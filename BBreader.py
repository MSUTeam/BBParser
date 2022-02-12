import os
import sqlite3
import shutil
import sys
from tkinter import filedialog
from tkinter import *
from tkinter.messagebox import askyesno
from bs4 import BeautifulSoup
from os import path
from string import Template
from contextlib import contextmanager



@contextmanager
def db_ops(db_name):
   conn = sqlite3.connect(db_name)
   cur = conn.cursor()
   yield cur
   conn.commit()
   conn.close()

root = Tk()
global DEBUGGING


# Base Class, some type of command that treats the passed data in a specific way
class CommandOption:
   def __init__(self, _id, _modID, _database):
      self.id = _id
      self.modID = _modID
      self.database = _database #unused right now, each mod has their own DB
      self.dbTableKey = self.database.dbFolder + self.scrub(self.modID) + ".db"
      

   def initDatabase(self):
      with db_ops(self.dbTableKey) as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + self.id + " (test text)")

   def returnWriteResult(self, _result):
      return "\nMod {modID} wrote option {id}: {result}".format(modID = self.modID, id = self.id, result = _result)

   def returnFileHeader(self):
      return 'this.logInfo("{modID}::{id} is being executed");\n'.format(modID = self.modID, id = self.id)


   def scrub(self, table_name):
    return ''.join( chr for chr in table_name if chr.isalnum() )

   def handleAction(self, action):
      pass

   def writeToFile(self, _file, _fileObj):
      pass

#Simple type that doesn't write to the DB
class WriteString(CommandOption):
   def __init__(self, _id, _modID, _database):
      super().__init__(_id, _modID, _database)
      self.toPrint = ""

   def handleAction(self, action):
      self.toPrint += "\n" + action[2]

   def writeToFile(self, _file, _fileObj):
      with open(_file + ".nut", 'a') as f:
         f.write(self.returnFileHeader())
         f.write(self.toPrint)
      _fileObj.TotalWritten.append(self.returnWriteResult(self.toPrint))
      self.toPrint = ""

#Type that writes to DB and prints all rows
class WriteDatabase(CommandOption):
   def __init__(self,  _id, _modID, _database, _template, _templateArguments):
      super().__init__( _id, _modID, _database)
      self.Template = _template 
      self.TemplateArguments = _templateArguments
      self.initDatabase()

   def initDatabase(self):
      columns = " ("
      for idx, colName in enumerate(self.TemplateArguments):
         columns += colName + " text"
         if idx != len(self.TemplateArguments) -1:
            columns += ", "
      columns += ")"
      with db_ops(self.dbTableKey) as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + self.id + columns)

   def writeToFile(self, _file, _fileObj):
      with db_ops(self.dbTableKey) as cur:
         cur.execute("SELECT * FROM " + self.id)
         with open(_file + ".nut", 'w') as f:
            f.write(self.returnFileHeader())
            rows = cur.fetchall()
            for row in rows:
               argmap = {}
               for idx, arg in enumerate(self.TemplateArguments):
                  argmap[arg] = row[idx]
               temp = Template(self.Template)
               sub = temp.substitute(argmap)
               f.write(sub)
               _fileObj.TotalWritten.append(self.returnWriteResult(sub))


class WriteModSetting(WriteDatabase):
   def handleAction(self, action):
      action = [self.scrub(entry) for entry in action]
      modID = action[1]
      settingID = action[2]
      value = action[3]
      with db_ops(self.dbTableKey) as cur:
         cur.execute("SELECT * FROM " + self.id + " WHERE settingID = ?", (settingID,))
         rows = cur.fetchall()
         if(len(rows) == 0):
            cur.execute("INSERT INTO " + self.id + " VALUES (?, ?, ?)" , (modID, settingID, value))
         else:
            cur.execute("UPDATE " + self.id + " SET value = :value WHERE modID = :modID and settingID = :settingID", {"value" : value, "modID" : modID, "settingID" : settingID })

class WriteKeybind(WriteDatabase):
   def scrub(self, table_name):
      return ''.join( chr for chr in table_name if (chr.isalnum() or chr == "+" or chr == "_"))

   def handleAction(self, action):
      action = [self.scrub(entry) for entry in action]
      settingID = action[2]
      value = action[3]
      with db_ops(self.dbTableKey) as cur:
         cur.execute("SELECT * FROM " + self.id + " WHERE settingID = ?", (settingID,))
         rows = cur.fetchall()
         if(len(rows) == 0):
            cur.execute("INSERT INTO " + self.id + " VALUES (?, ?)" , (settingID, value))
         else:
            cur.execute("UPDATE " + self.id + " SET value = :value WHERE settingID = :settingID", {"value" : value, "settingID" : settingID })



#manages all the CommandOptions to categorise them into Mods, parses the commands and outputs to the files
class ParseManager:
   def __init__(self, _database):
      self.TotalWritten = []
      self.Mods = {}
      self.Options = {
         "ModSetting" : WriteModSetting, 
         "Default" : WriteString,
         "Keybind" : WriteKeybind
      }
      self.database = _database # could use that idk

   def parse(self, _path):
      commands = self.getCommands(_path)
      for command in commands:
         commandType = command[0]
         modName = command[1]
         if modName not in self.Mods:
            self.Mods[modName] = {
               "Options"  : {}
            }
         mod = self.Mods[modName]
         if (commandType in mod["Options"]) == False:
            
            if commandType == "ModSetting":
               mod["Options"][commandType] = WriteModSetting(commandType, modName, self.database, """this.MSU.SettingsManager.updateSetting("$modID", "$settingID", $value);\n""", ["modID", "settingID", "value"])
            elif commandType == "Keybind":
               mod["Options"][commandType] = WriteKeybind(commandType, modName, self.database, """this.MSU.CustomKeybinds.set("$settingID", "$value");\n""", ["settingID", "value"])
            else:
               mod["Options"][commandType] = WriteString(commandType, modName, self.database)

         mod["Options"][commandType].handleAction(command)

   def scrub(self, table_name):
      return ''.join( chr for chr in table_name if chr.isalnum() )

   def getCommands(self, _path):
      results = []
      with open(_path) as fp:
         soup = BeautifulSoup(fp, "html.parser")
         logInfoArray = soup.findAll(class_ = "text")
         for entry in logInfoArray:
            contents = entry.contents[0].split(";")
            if contents[0] == "PARSEME":
               results.append(contents[1:])
      return results

   def write_files(self, _path):
      if path.isdir(_path) == False:
            os.mkdir(_path)
      for mod, modContents in self.Mods.items():
         modPath = path.join(_path, mod)
         if path.isdir(modPath) == False:
            os.mkdir(modPath)
         for option, optionContents in modContents.items():
            for optionType, optionClass in optionContents.items():
               typePath = path.join(modPath, optionType)
               optionClass.writeToFile(typePath, self)



# Handles the Database connection
class Database:
   def __init__(self, _databaseName):
      self.databaseName = _databaseName
      self.gui = None
      self.dbFolder = "./mod_db/"
      self.initDatabase()

   def initDatabase(self):
      self.modConfigPath = None
      self.logPath = None
      with db_ops(self.databaseName) as cur:
         cur.execute('CREATE TABLE IF NOT EXISTS paths (type text, path text)')
         cur.execute('SELECT path FROM paths WHERE type="data"')
         gamedir = cur.fetchone()
         if(gamedir != None):
            self.modConfigPath = gamedir[0]
         else:
            cur.execute('INSERT INTO paths VALUES ("data", Null)')


         cur.execute('SELECT path FROM paths WHERE type="log"')
         logdir = cur.fetchone()
         if(logdir != None):
            self.logPath = logdir[0]
         else:
            cur.execute('INSERT INTO paths VALUES ("log", Null)')
      if path.isdir(self.dbFolder) == False:
            os.mkdir(self.dbFolder)


   def UpdateGameDirectory(self, _path):
      self.modConfigPath = _path
      with db_ops(self.databaseName) as cur:
         cur.execute("""UPDATE paths SET path = ? WHERE type = 'data'""", (self.modConfigPath,))
      
   def UpdateLogDirectory(self, _path):
      self.logPath = _path
      with db_ops(self.databaseName) as cur:
         cur.execute("""UPDATE paths SET path = ? WHERE type = 'log'""", (self.logPath,))
   
   def IsReadyToRun(self):
      return self.modConfigPath != None and self.logPath != None



   def RunParse(self, _input = None):
      parsemanager = ParseManager(self)
      if _input != None:
         global DEBUGGING
         if _input.rstrip() == "ENABLE DEBUG":
            DEBUGGING = True
            self.gui.AddMsg("DEBUGGING ENABLED")
            self.gui.UpdateOutput()
            return
         elif _input.rstrip() == "DISABLE DEBUG":
            DEBUGGING = False
            print("DEBUGGING ENABLED")
            self.gui.AddMsg("DEBUGGING ENABLED")
            self.gui.UpdateOutput()
            return

         self.writeInputLog(_input)
         parsemanager.parse("local_log.html")
         parsemanager.write_files("./mod_config")
         os.remove("local_log.html")
      elif DEBUGGING:
         self.WriteTestLog()
         parsemanager.parse("log.html")
         parsemanager.write_files("./mod_config")
         os.remove("log.html")
      else:
         parsemanager.parse(self.logPath)
         parsemanager.write_files(self.modConfigPath)

      for msg in parsemanager.TotalWritten:
         self.gui.AddMsg(msg)
      self.gui.AddMsg("Completed!")
      self.gui.UpdateOutput()

   #this can be expanded to parse things further
   def writeInputLog(self, _input):
      with open("local_log.html", "w") as log:
         for line in _input.split(";"):
            log.write("""<div class="text">PARSEME;Global;MSU;""" + line.rstrip() + """</div>""")

   def WriteTestLog(self):
      with open("log.html", "w") as log:
         log.write("""<div class="text">PARSEME;String;Vanilla;this.logInfo("Hello, World!");</div>""")


         # log.write("""<div class="text">PARSEME;ModSetting;MSU;logall;true;</div>""")
         # log.write("""<div class="text">PARSEME;ModSetting;MSU;logall;false;</div>""")
         # log.write("""<div class="text">PARSEME;ModSetting;MSU;logall;true;</div>""")
         # log.write("""<div class="text">PARSEME;PerkBuild;PlanPerks;this.World.Perks.importPerkBuilds("124$perk.hold_out#1+perk.rotation#1+perk.bags_and_belts#1+perk.mastery.polearm#1+~");</div>""")
         # for x in range(100):
         #    log.write("<div class='text'>PARSEME;Keybind;MSU;{idx};c+ctrl</div>".format(idx = x))

   def RemoveDB(self, _fileName):
      _path = self.dbFolder + _fileName + ".db"
      if path.isfile(_path):
         self.gui.AddMsg("Deleted database " + _path)
         os.remove(_path)

   def RemoveFromDB(self, _modID, _settingID):
      _path = self.dbFolder + _modID + ".db"
      if path.isfile(_path):
         with db_ops(_path) as cur:
            cur.execute("DROP TABLE IF EXISTS " + _settingID)
            self.gui.AddMsg("Deleted data " + _settingID + " from database " + _path)

   def DeleteAllSettings(self):
      os.remove(self.databaseName)
      if path.isdir(self.dbFolder):
         self.gui.AddMsg("Deleted folder " + self.dbFolder)
         shutil.rmtree(self.dbFolder)
      if DEBUGGING:
         if path.isdir("./mod_config"):
            self.gui.AddMsg("Deleted folder ./mod_config")
            shutil.rmtree("./mod_config")
      else:
         if self.modConfigPath != None and path.isdir(self.modConfigPath):
            self.gui.AddMsg("Deleted folder " + self.modConfigPath)
            shutil.rmtree(self.modConfigPath)
         
      self.initDatabase()

   def DeleteModSettings(self, _modID):
      pass
      



# Handles the GUI element
class GUI:
   def __init__(self, _database):
      self.database = _database
      self.database.gui = self
      self.PendingOutput = []

      self.titleLabel = Label(root, text="Battle Brothers Reader")
      self.titleLabel.grid(row=0, column=0)
      self.dbNameLabel = Label(root, text="Database: " + self.database.databaseName)
      self.dbNameLabel.grid(row=0, column=1)

      self.dataPathVar = StringVar(root, "Browse to your game directory")
      self.dataPathLabel = Label(root, textvariable = self.dataPathVar)
      self.dataPathLabel.grid(row=3, column=0)
      self.dataPathButton =  Button(text="Browse", command=self.UpdateGameDirectory)
      self.dataPathButton.grid(row=3, column=1)
      
      self.logPathVar = StringVar(root, "Browse to your log.html directory (documents/Battle Brothers/)")
      self.logPathLabel = Label(root, textvariable = self.logPathVar)
      self.logPathLabel.grid(row=4, column=0)
      self.logPathButton =  Button(text="Browse", command=self.UpdateLogDirectory)
      self.logPathButton.grid(row=4, column=1)

      self.deleteSingleSettingLabel = Label(root, text = "Delete a setting file and any related data.")
      self.deleteSingleSettingLabel.grid(row=5, column=0)
      self.deleteSingleSettingButton = Button(root, text="Delete specific setting", command=self.DeleteSingleSetting, state="disabled")
      self.deleteSingleSettingButton.grid(row=5, column=1)

      self.deleteSingleSettingLabel = Label(root, text = "Delete all settings for a select mod folder.")
      self.deleteSingleSettingLabel.grid(row=6, column=0)
      self.deleteSingleModButton = Button(root, text="Delete mod settings", command=self.DeleteSingleMod, state="disabled")
      self.deleteSingleModButton.grid(row=6, column=1)

      self.deleteAllLabel = Label(root, text = "Delete all settings to get a clean install")
      self.deleteAllLabel.grid(row=7, column=0)
      self.deleteAllButton = Button(root, text="Delete all settings", command=self.DeleteAllSettings, state="active")
      self.deleteAllButton.grid(row=7, column=1)

      self.runFileButton = Button(root, text="Update settings", command=self.RunFileParse, state="disabled")
      self.runFileButton.grid(row=8, column=0)

      self.runInputButton = Button(root, text="Execute current input", command=self.RunInputParse, state="active")
      self.runInputButton.grid(row=8, column=1)


      self.ResultEntry = Text(root)
      self.ResultEntry.grid(row=9, column = 0)
      self.UpdateStringVarText(self.dataPathVar, self.database.modConfigPath if self.database.modConfigPath != None else "Browse to your game directory")
      self.UpdateStringVarText(self.logPathVar, self.database.logPath if self.database.logPath != None else "Select your log.html file (documents/Battle Brothers/log.html)")
      self.UpdateButtons()
      if(DEBUGGING):
         self.AddMsg("DEBUGGING ENABLED")
         self.UpdateOutput()


      

   def UpdateGameDirectory(self):
      directory = filedialog.askdirectory()
      if directory == None or len(directory.split("/")) < 2 or directory.split("/")[-1] != "data":
         self.AddMsg("Bad Path! " + str(directory))
      else:
         self.database.UpdateGameDirectory(directory+"/mod_config")
         self.UpdateStringVarText(self.dataPathVar, self.database.modConfigPath)
         self.AddMsg("Directory selected successfully! " + str(directory))
      self.UpdateButtons()
      self.UpdateOutput()
         
   def UpdateLogDirectory(self):
      directory = filedialog.askopenfile(mode ='r', filetypes =[('log.html', 'log.html')])
      if directory == None or directory.name.split("/")[-1] != "log.html":
         self.AddMsg("Bad Path! " + str(directory))
      else:
         self.database.UpdateLogDirectory(directory.name)
         self.UpdateStringVarText(self.logPathVar, self.database.logPath)
         self.AddMsg("log file selected successfully! " + directory.name)
      self.UpdateButtons()
      self.UpdateOutput()

   def UpdateStringVarText(self, _stringvar, _text):
      _stringvar.set(_text)


   def UpdateButtonStatus(self, _button, _bool):
      if _bool:
         _button.config(state = "active")
      else:
         _button.config(state = "disabled")

   def UpdateButtons(self):
      self.UpdateButtonStatus(self.runFileButton, self.database.IsReadyToRun())
      self.UpdateButtonStatus(self.deleteSingleModButton, self.database.modConfigPath != None)
      self.UpdateButtonStatus(self.deleteSingleSettingButton, self.database.modConfigPath != None)

   def ResetStringVars(self):
      self.UpdateStringVarText(self.dataPathVar, "Browse to your game directory")
      self.UpdateStringVarText(self.logPathVar, "Select your log.html file (documents/Battle Brothers/log.html)")


   def RunFileParse(self):
      self.ClearOutput()
      self.AddMsg("Trying to parse file")
      self.database.RunParse()

   def RunInputParse(self):
      self.AddMsg("Trying to parse input")
      text = self.ResultEntry.get("1.0",END)
      self.database.RunParse(text)

   def DeleteAllSettings(self):
      answer = askyesno("Delete all settings", "Are you sure? This will delete all files in your mod_config and the database.")
      if answer:
         self.ClearOutput()
         self.ResetStringVars()
         self.UpdateButtons()
         self.database.DeleteAllSettings()
      self.UpdateOutput()

   def DeleteSingleSetting(self):
      directory = filedialog.askopenfile(filetypes =[('nut files', '*.nut')])
      if(directory != None):
         path = directory.name
         directory = None
         self.AddMsg("Deleting setting " + path)
         os.remove(path)
         modName = path.split("/")[-2]
         filename = path.split("/")[-2]
         self.database.RemoveFromDB(modName, filename)
      self.UpdateOutput()


   def DeleteSingleMod(self):
      directory = filedialog.askdirectory()
      if directory == None or len(directory.split("/")) < 2 or directory.split("/")[-2] != "mod_config":
         self.AddMsg("Bad Path! " + directory)
      else:
         self.AddMsg("Deleting folder: " + directory)
         try: 
            shutil.rmtree(directory)
         except:
            self.AddMsg("Could not delete folder: " + directory)
         else:
            self.AddMsg("Deleted folder: " + directory)

         self.database.RemoveDB(directory.split("/")[-1])
      self.UpdateOutput()
      

   def AddMsg(self, _text, _newline = True):
      if _newline:
         _text += "\n"
      
      self.PendingOutput.append(_text)

   def UpdateOutput(self):
      result = ""
      while len(self.PendingOutput) > 0:
         text = self.PendingOutput.pop(0)
         result+=text
         if(DEBUGGING):
            print(text)
      self.ResultEntry.insert(END, result)
      


   def ClearOutput(self):
      self.ResultEntry.delete('1.0', END)
      self.PendingOutput = []




global DBNAME
if(len(sys.argv) > 1):
   DBNAME = sys.argv[1]
else:
   DBNAME = 'mod_settings.db'

defaultDB = Database(DBNAME)

#if reads to a local file and writes results in directory of exe
DEBUGGING = False

gui = GUI(defaultDB)



root.mainloop()