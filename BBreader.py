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


# Base Class, some type of command that treats the passed data in a specific way
class Option:
   def __init__(self, _id, _modID, _database):
      self.id = _id
      self.modID = _modID
      self.database = _database
      self.dbkey = self.scrub(self.modID + self.id)
      

   def initDatabase(self):
      with db_ops(self.database.databaseName) as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + self.dbkey + " (test text)")

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
class WriteString(Option):
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
class WriteDatabase(Option):
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
      print(self.dbkey + columns)
      with db_ops(self.database.databaseName) as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + self.dbkey + columns)

   def writeToFile(self, _file, _fileObj):
      with db_ops(self.database.databaseName) as cur:
         cur.execute("SELECT * FROM " + self.dbkey)
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
      with db_ops(self.database.databaseName) as cur:
         cur.execute("SELECT * FROM " + self.dbkey + " WHERE settingID = ?", (settingID,))
         rows = cur.fetchall()
         if(len(rows) == 0):
            cur.execute("INSERT INTO " + self.dbkey + " VALUES (?, ?, ?)" , (modID, settingID, value))
         else:
            cur.execute("UPDATE " + self.dbkey + " SET value = :value WHERE modID = :modID and settingID = :settingID", {"value" : value, "modID" : modID, "settingID" : settingID })

class WriteKeybind(WriteDatabase):
   def scrub(self, table_name):
      return ''.join( chr for chr in table_name if (chr.isalnum() or chr == "+" or chr == "_"))

   def handleAction(self, action):
      action = [self.scrub(entry) for entry in action]
      settingID = action[2]
      value = action[3]
      with db_ops(self.database.databaseName) as cur:
         cur.execute("SELECT * FROM " + self.dbkey + " WHERE settingID = ?", (settingID,))
         rows = cur.fetchall()
         if(len(rows) == 0):
            cur.execute("INSERT INTO " + self.dbkey + " VALUES (?, ?)" , (settingID, value))
         else:
            cur.execute("UPDATE " + self.dbkey + " SET value = :value WHERE settingID = :settingID", {"value" : value, "settingID" : settingID })


class ParseObject:
   def __init__(self, _database):
      self.TotalWritten = []
      self.Mods = {}
      self.Options = {
         "ModSetting" : WriteModSetting, 
         "Default" : WriteString,
         "Keybind" : WriteKeybind
      }
      self.database = _database # could use that idk
      ResultEntry.delete('1.0', END)

   def parse(self, _alternateFilePath = None):
      commands = self.getCommands(_alternateFilePath)
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
               mod["Options"][commandType] = WriteModSetting(commandType, modName, self.database, """this.MSU.SettingsManager.updateSetting("$modID", "$settingID", $value)""", ["modID", "settingID", "value"])
            elif commandType == "Keybind":
               mod["Options"][commandType] = WriteKeybind(commandType, modName, self.database, """this.MSU.CustomKeybinds.set("$settingID", "$value")""", ["settingID", "value"])
            else:
               mod["Options"][commandType] = WriteString(commandType, modName, self.database)

         mod["Options"][commandType].handleAction(command)

   def scrub(self, table_name):
      return ''.join( chr for chr in table_name if chr.isalnum() )

   def getCommands(self, _alternateFilePath):
      results = []
      filepath = self.database.logpath + "/log.html" if _alternateFilePath == None else _alternateFilePath
      with open(filepath) as fp:
         soup = BeautifulSoup(fp, "html.parser")
         logInfoArray = soup.findAll(class_ = "text")
         for entry in logInfoArray:
            contents = entry.contents[0].split(";")
            if contents[0] == "PARSEME":
               results.append(contents[1:])
      return results

   def write_files(self):
      modConfigPath = self.database.gamepath + "/mod_config"
      for mod, modContents in self.Mods.items():
         modPath = path.join(modConfigPath, mod)
         if path.isdir(modPath) == False:
            os.mkdir(modPath)
         for option, optionContents in modContents.items():
            for optionType, optionClass in optionContents.items():
               typePath = path.join(modPath, optionType)
               optionClass.writeToFile(typePath, self)
      for msg in self.TotalWritten:
         ResultEntry.insert(END, msg)




class Database:
   def __init__(self, _databaseName):
      self.databaseName = _databaseName
      self.initDatabase()

   def initDatabase(self):
      self.gamepath = None
      self.logpath = None
      with db_ops(self.databaseName) as cur:
         cur.execute('CREATE TABLE IF NOT EXISTS paths (type text, path text)')
         cur.execute('SELECT path FROM paths WHERE type="data"')
         gamedir = cur.fetchone()
         if(gamedir != None):
            self.gamepath = gamedir[0]
         else:
            cur.execute('INSERT INTO paths VALUES ("data", Null)')


         cur.execute('SELECT path FROM paths WHERE type="log"')
         logdir = cur.fetchone()
         if(logdir != None):
            self.logpath = logdir[0]
         else:
            cur.execute('INSERT INTO paths VALUES ("log", Null)')


   def UpdateGameDirectory(self):
      directory = filedialog.askdirectory()
      if directory.split("/")[-1] != "data":
         textGamePath.config(text = "Bad Directory!")
      else:
         self.gamepath = directory
         textGamePath.config(text = self.gamepath)
         modConfigPath = self.gamepath + "/mod_config"
         if path.isdir(modConfigPath) == False:
               os.mkdir(modConfigPath)

      self.checkButtonStatus()
   

   def UpdateLogDirectory(self):
      directory = filedialog.askdirectory()
      if directory.split("/")[-1] != "Battle Brothers":
         textLogPath.config(text = "Bad Directory!")
      else:
         self.logpath = directory
         textLogPath.config(text = self.logpath)

      self.checkButtonStatus()
   
   def isButtonValid(self):
      return self.gamepath != None and self.logpath != None

   def checkButtonStatus(self):
      if self.isButtonValid():
         textGamePath.config(text = self.gamepath)
         textLogPath.config(text = self.logpath)
         runButton.config(state = "normal")
         with db_ops(self.databaseName) as cur:
            cur.execute("""UPDATE paths SET path = ? WHERE type = 'log'""", (self.logpath,))
            cur.execute("""UPDATE paths SET path = ? WHERE type = 'data'""", (self.gamepath,))
      else:
         runButton.config(state = "disabled")

   def UpdateText(self):
      parseobj = ParseObject(self)
      if DEBUGGING:
         self.WriteTestLog()
         parseobj.parse("log.html")
      else:
         parseobj.parse()
      parseobj.write_files()

   def WriteTestLog(self):
      with open("log.html", "w") as log:
         log.write("""<div class="text">PARSEME;String;Vanilla;this.logInfo("Hello, World!");</div>""")
         log.write("""<div class="text">PARSEME;String;MSU;this.MSU.SettingsManager.updateSetting("MSU", "logall", false);</div>""")
         log.write("""<div class="text">PARSEME;ModSetting;MSU;logall;true;</div>""")

         log.write("""<div class="text">PARSEME;Keybind;MSU;character_toggleCharacterMenu_1;c+ctrl</div>""")


   def DeleteAllSettings(self):
      answer = askyesno("Delete all settings", "Are you sure? This will delete all files in your mod_config and the database.")
      if answer:
         os.remove(self.databaseName)
         ResultEntry.delete('1.0', END)
         if self.gamepath != None and path.isdir(self.gamepath+"/mod_config"):
            shutil.rmtree(self.gamepath+"/mod_config")
         self.initDatabase()
         textGamePath.config(text = "Browse to your game directory")
         textLogPath.config(text = "Browse to your log.html directory (documents/Battle Brothers/)")
         self.checkButtonStatus()

   def DeleteModSettings(self):
      pass
      

global DBNAME
if(len(sys.argv) > 1):
   DBNAME = sys.argv[1]
else:
   DBNAME = 'mod_settings.db'

defaultDB = Database(DBNAME)

global DEBUGGING
DEBUGGING = True

# ------------------------------------------------ visuals -----------------------------------------

textHeading = Label(root, text="Battle Brothers Reader, database: " + DBNAME)
textHeading.grid(row=0, column=0)
textGamePath = Label(root, text = "Browse to your game directory")
textGamePath.grid(row=3, column=0)
buttonDirectory =  Button(text="Browse", command=defaultDB.UpdateGameDirectory)
buttonDirectory.grid(row=3, column=1)
textLogPath = Label(root, text="Browse to your log.html directory (documents/Battle Brothers/)")
textLogPath.grid(row=4, column=0)
buttonDirectory =  Button(text="Browse", command=defaultDB.UpdateLogDirectory)
buttonDirectory.grid(row=4, column=1)

runButton = Button(root, text="Update settings", command=defaultDB.UpdateText, state="disabled")
runButton.grid(row=5, column=0)

deleteButton = Button(root, text="Delete settings", command=defaultDB.DeleteAllSettings, state="active")
deleteButton.grid(row=5, column=1)

ResultEntry = Text(root)
ResultEntry.grid(row=6)

defaultDB.checkButtonStatus()






root.mainloop()