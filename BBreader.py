import os
import sqlite3
import shutil
import sys
from tkinter import filedialog
from tkinter import *
from tkinter.messagebox import askyesno
from os import path
from os import walk
from string import Template
from contextlib import contextmanager
from dataclasses import dataclass
import re



@contextmanager
def db_ops(db_name):
   conn = sqlite3.connect(db_name)
   cur = conn.cursor()
   yield cur
   conn.commit()
   conn.close()

def printDebug(_text):
   if DEBUGGING:
      print(_text)

def resource_path(relative_path):
   if hasattr(sys, '_MEIPASS'):
      return os.path.join(sys._MEIPASS, relative_path)
   return os.path.join(os.path.abspath("."), relative_path) 

root = Tk()


# The result of a command string extracted from the log or other
@dataclass
class CommandObject:
   commandType : str
   modID : str
   value : str
   extravalue : None

# Base Class for a command option, some type of command that treats the passed data in a specific way
class CommandOption:
   def getCommandClass(_database, _commandType, _modName):
      if _commandType == "ModSetting":
         return WriteModSetting(_commandType, _modName, _database)
      elif _commandType == "Keybind":
         return WriteKeybind(_commandType, _modName, _database)
      else:
         if (_commandType.find(":APPEND") != -1):
            _commandType = _commandType.split(":APPEND")[0]
            return WriteStringAppend(_commandType, _modName, _database)
         else:
            return WriteString(_commandType, _modName, _database)

   def __init__(self, _id, _modID, _database):
      self.commandType = _id
      self.modID = _modID
      self.database = _database 
      self.dbTableKey = self.database.dbFolder + self.modID + ".db"
      printDebug("Created new CommandOption obj: " + str(self))

   def returnWriteResult(self, _result):
      return "\nMod {modID} wrote option {commandType}: {result}".format(modID = self.modID, commandType = self.commandType, result = _result)

   def returnFileHeader(self):
      return 'this.logInfo("{modID}::{commandType} is being executed");\n'.format(modID = self.modID, commandType = self.commandType)

   def validateCommand(self, _commandObj):
      return True

   def handleCommand(self, _commandObj):
      pass

   def writeToFile(self, _file, _fileObj):
      pass

   def __str__ (self):
      return '{type}(commandType: {commandType} | Mod: {modID} | dbTableKey: {dbTableKey})'.format(type = self.__class__.__name__, commandType = self.commandType, modID = self.modID, dbTableKey = self.dbTableKey)

#Simple type that doesn't write to the DB
class WriteString(CommandOption):
   def __init__(self, _commandType, _modID, _database):
      super().__init__(_commandType, _modID, _database)
      self.toPrint = ""

   def handleCommand(self, _commandObj):
      self.toPrint = "\n" + _commandObj.value

   def writeToFile(self, _file, _fileObj):
      with open(_file + ".nut", 'a') as f:
         f.write(self.returnFileHeader())
         f.write(self.toPrint)
      _fileObj.TotalWritten.append(self.returnWriteResult(self.toPrint))
      self.toPrint = ""

class WriteStringAppend(WriteString):
   def handleCommand(self, _commandObj):
      self.toPrint += "\n" + _commandObj.value

#Type that writes to DB and prints all rows
class WriteDatabase(CommandOption):
   def __init__(self,  _commandType, _modID, _database, _template, _templateArguments):
      super().__init__( _commandType, _modID, _database)
      self.Template = _template 
      self.TemplateArguments = _templateArguments
      self.initDatabase()
      self.changedSinceLastUpdate = True
      self.toLog = [];

   def getTemplate(self, _modID, _settingID, _value):
      argmap = {}
      argmap["modID"] = _modID
      argmap["settingID"] = _settingID
      argmap["value"] = _value
      temp = Template(self.Template)
      sub = temp.substitute(argmap)
      return sub

   def initDatabase(self):
      columns = " ("
      for idx, colName in enumerate(self.TemplateArguments):
         columns += colName + " text"
         if idx != len(self.TemplateArguments) -1:
            columns += ", "
      columns += ")"
      with db_ops(self.dbTableKey) as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + self.commandType + columns)

   def writeToFile(self, _file, _fileObj):
      #only write to file if it had updates in last parsing loop
      if(self.changedSinceLastUpdate == False):
         return

      with db_ops(self.dbTableKey) as cur:
         cur.execute("SELECT * FROM " + self.commandType)
         with open(_file + ".nut", 'w') as f:
            f.write(self.returnFileHeader())
            rows = cur.fetchall()
            for row in rows:
               f.write(self.getTemplate(row[0], row[1], row[2]))
               
      for line in self.toLog:
         _fileObj.TotalWritten.append(self.returnWriteResult(line))
      self.toLog = []
      self.changedSinceLastUpdate = False

   def handleCommand(self, _commandObj):
      self.changedSinceLastUpdate = True
      _commandObj.extravalue = _commandObj.extravalue[0]
      with db_ops(self.dbTableKey) as cur:
         cur.execute("SELECT * FROM " + self.commandType + " WHERE settingID = ?", (_commandObj.value,))
         rows = cur.fetchall()
         if(len(rows) == 0):
            cur.execute("INSERT INTO " + self.commandType + " VALUES (?, ?, ?)" , (_commandObj.modID, _commandObj.value, _commandObj.extravalue))
         else:
            cur.execute("UPDATE " + self.commandType + " SET value = :value WHERE modID = :modID and settingID = :settingID", {"value" : _commandObj.extravalue, "modID" : _commandObj.modID, "settingID" : _commandObj.value })
         self.toLog.append(self.getTemplate(_commandObj.modID, _commandObj.value, _commandObj.extravalue))

      


# Ingame mod settings menu
class WriteModSetting(WriteDatabase):
   def __init__(self,  _commandType, _modID, _database):
      super().__init__( _commandType, _modID, _database, """this.MSU.System.ModSettings.setSettingFromPersistence("$modID", "$settingID", $value);\n""", ["modID", "settingID", "value"])


# Custom keybind handler settings menu option
class WriteKeybind(WriteDatabase):
   def __init__(self,  _commandType, _modID, _database):
      super().__init__( _commandType, _modID, _database, """this.MSU.System.Keybinds.updateFromPersistence("$modID", "$settingID", "$value");\n""", ["modID", "settingID", "value"])


class Mod:
   def __init__(self, _modID, _path, _dbPath):
      self.ModID = _modID
      self.ConfigPath = _path
      self.DBPath = _dbPath
      self.Options = {}
      printDebug("Created new Mod obj: " + str(self))

   def __str__ (self):
      result = 'Mod(ModID: {modid} | ConfigPath: {configpath} | DBPath: {dbpath})'.format(modid = self.ModID, configpath = self.ConfigPath, dbpath = self.DBPath)
      return result



##reintroduce parse object? does all the parsing stuff, advantage of being easily removed and reinitialised between sessions
# class ParseObject:
#    def __init__(self, _database, _mods, _configpath, _logpath):
#       self.database = _database
#       self.mods = _mods
#       self.configpath = configpath
#       self.logpath = _logpath
         # self.PreviousReadIndex = 0
         # self.StopLoop = False
         # self.LastUpdateTime = None
         # self.LastBootTime = None


class LoopDone(Exception):
   pass


#manages all the CommandOptions to categorise them into Mods, parses the commands and outputs to the files
# Handles the Database connection

class Database:
   def __init__(self, _databaseName):
      self.databaseName = _databaseName
      self.gui = None
      self.dbFolder = "./mod_db/"
      self.TotalWritten = []
      self.Mods = {}
      self.PreviousReadIndex = 0
      self.StopLoop = False
      self.LastUpdateTime = None
      self.LastBootTime = None
      self.initDatabase()
      self.getExistingModFiles()

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

   def getExistingModFiles(self):
      if self.modConfigPath == None or path.isdir(self.modConfigPath) == False:
         return
      idx = 0
      for (dirpath, dirnames, filenames) in os.walk(self.modConfigPath):
         if (idx == 0):
            for name in dirnames:
               if name not in self.Mods:
                  self.Mods[name] = Mod(name, dirpath+"/"+name, self.dbFolder + name + ".db")
                  printDebug("Added mod: " + str(self.Mods[name]))
         else:
            modname = dirpath.split("\\")[-1]
            for filename in filenames:
               filename = filename.split(".")[0]
               if filename not in self.Mods[modname].Options:
                  self.Mods[modname].Options[filename] = CommandOption.getCommandClass(self, filename, modname)
         idx += 1

   def updateGameDirectory(self, _path):
      self.modConfigPath = _path
      with db_ops(self.databaseName) as cur:
         cur.execute("""UPDATE paths SET path = ? WHERE type = 'data'""", (self.modConfigPath,))
      
   def updateLogDirectory(self, _path):
      self.logPath = _path
      with db_ops(self.databaseName) as cur:
         cur.execute("""UPDATE paths SET path = ? WHERE type = 'log'""", (self.logPath,))

   
   def isReadyToRun(self):
      return self.modConfigPath != None and self.logPath != None

   def parseLocalInput(self, _input):
      global DEBUGGING
      if _input.rstrip() == "DEBUG":
         DEBUGGING = True
         self.gui.addMsg("DEBUGGING ENABLED")
         self.setDebug(True)
         self.gui.updateOutput()
         return
      elif _input.rstrip() == "!DEBUG":
         DEBUGGING = False
         self.setDebug(False)
         self.gui.addMsg("DEBUGGING DISABLED")
         self.gui.updateOutput()
         return
      else:
         self.writeInputLog(_input)
         self.parse("local_log.html")
         self.writeFiles("./mod_config")
         os.remove("local_log.html")


   def parseLogInLoop(self):
      #main loop, uses a try - else structure with root.after timeouts
      try:
         if self.StopLoop == True:
            raise LoopDone

         currentTimeFromLog = os.path.getmtime(self.logPath)

         if self.LastUpdateTime != currentTimeFromLog:
            self.LastUpdateTime = currentTimeFromLog
            
            if self.isNewBoot():
               self.resetReadIndex()
           
            self.parse(self.logPath)
            self.writeFiles(self.modConfigPath)
            for msg in self.TotalWritten:
               self.gui.addMsg(msg)
            self.gui.updateOutput()
            self.TotalWritten = []

      except LoopDone as e:
         self.gui.addMsg("Completed!")
         self.gui.updateOutput()
         self.clearLoopVars()
         if DEBUGGING:
            os.remove("./log.html")

      except Exception as e:
         print("BBParser encountered an error: " +  str(e))

      except IOError as e:
         self.gui.addMsg("Could not open log.html!")
         self.gui.updateOutput()
         if DEBUGGING:
            os.remove("./log.html")  

      else: 
          root.after(1000, self.parseLogInLoop)

   def getBootTime(self):
      # gets time info of first entry ín the log
      with open(self.logPath) as fp:  
         time = re.search('(?:<div class="time">)(\d\d:\d\d:\d\d)(?:<\/div>)', fp.readline()).group(1)
         return [int(num) for num in time.split(":")]


   def setBootTime(self):
      self.LastBootTime = self.getBootTime()
   

   def isNewBoot(self):
      # See if the game has been restarted and we need to index from 0 again
      if self.LastBootTime == None:
         self.setBootTime()
         return True

      currentBootTime = self.getBootTime()
      for num1, num2 in zip(currentBootTime, self.LastBootTime):
         if num1 > num2:
            self.setBootTime()
            return True

      return False

   def clearLoopVars(self):
      self.TotalWritten = []
      self.LastBootTime = None
      self.LastUpdateTime = None
      self.resetReadIndex()
      self.StopLoop = False
      global DEBUGGING
      if DEBUGGING:
         self.writeTestLog()

   def parse(self, _path):
      commands = self.getCommandsFromLog(_path)
      for command in commands:
         commandObj = self.getCommandObj(command)
         if commandObj == False:
            continue
         self.increaseReadIndex()
         commandType = commandObj.commandType
         modID = commandObj.modID
         if commandObj.modID not in self.Mods:
            self.Mods[modID] = Mod(modID, self.modConfigPath + "/" + modID, self.dbFolder + "/" + modID + ".db")
         modOptions = self.Mods[modID].Options
         if (commandType in modOptions) == False or modOptions[commandType] == None:
            modOptions[commandType] = CommandOption.getCommandClass(self, commandType, modID)
         modOptions[commandType].handleCommand(commandObj)


   def getCommandObj(self, _command):
      _command = [self.scrub(entry) for entry in _command]
      extravalue = None
      if(len(_command)) < 3:
         print("Command " + str(_command) + " is not valid!")
         return False
      if len(_command) > 3:
         extravalue = _command[3:]
      commandObj = CommandObject(_command[0], _command[1], _command[2], extravalue)
      print(commandObj)
      return commandObj

   def increaseReadIndex(self, _value = 1):
      self.PreviousReadIndex += _value

   def resetReadIndex(self):
      self.PreviousReadIndex = 0

   def getCommandsFromLog(self, _path):
      with open(_path) as fp: 
         regexResult = re.findall('(?:<div class="text">BBPARSER;)(.+?)(?=<\/div>)', fp.readline())
         result = list(map(lambda entry: entry.split(";"), regexResult))[self.PreviousReadIndex:]
         return result

   def writeFiles(self, _path):
      if path.isdir(_path) == False:
            os.mkdir(_path)
      for mod, modObj in self.Mods.items():
         modPath = path.join(_path, mod)
         if path.isdir(modPath) == False:
            os.mkdir(modPath)
         for optionType, optionObj in modObj.Options.items():
            typePath = path.join(modPath, optionType)
            optionObj.writeToFile(typePath, self)

   #this can be expanded to parse things further
   def writeInputLog(self, _input):
      with open("local_log.html", "w") as log:
         for line in _input.split(";"):
            log.write("""<div class="text">BBPARSER;Global;MSU;""" + line.rstrip() + """</div>""")

   def delete(self, _arg):
      if(_arg == ""):
         return
      result = _arg.split(":")
      if(len(result) == 1):
         self.deleteMod(result[0])

      elif(len(result) == 2):
         self.deleteOptionFromMod(result[0].rstrip(), result[1].lstrip())

      self.gui.updateOutput()

   def deleteMod(self, _modID):
      mod = self.Mods[_modID]
      directory = mod.ConfigPath
      db_directory = mod.DBPath
      try: 
         shutil.rmtree(directory)
         self.gui.addMsg("Deleted folder: " + directory)
      except Exception as e:
         self.gui.addMsg("Could not delete folder " + str(directory) + " : " + str(e))
        
      self.removeDB(db_directory)
      del self.Mods[_modID]

   def deleteOptionFromMod(self, _modID, _commandType):
      mod = self.Mods[_modID]
      directory = mod.ConfigPath + "/" + _commandType +".nut"
      db_directory = mod.DBPath
      try: 
         os.remove(directory)
         self.gui.addMsg("Deleted folder: " + directory)
      except Exception as e:
         self.gui.addMsg("Could not delete folder " + directory + " : " + e)
        
      self.removeFromDB(db_directory, _commandType)
      del mod.Options[_commandType]


   def removeDB(self, _path):
      if path.isfile(_path):
         try:
            os.remove(_path)
            self.gui.addMsg("Deleted database " + _path)
         except:
            self.gui.addMsg("Could not delete database " + _path)
         

   def removeFromDB(self, _path, _commandType):
      if path.isfile(_path):
         try:
            with db_ops(_path) as cur:
               cur.execute("DROP TABLE IF EXISTS " + _commandType)
            self.gui.addMsg("Deleted data " + _commandType + " from database " + _path)
         except:
            self.gui.addMsg("Could not delete data " + _commandType + " from database " + _path)
         

   def deleteAllSettings(self):
      os.remove(self.databaseName)

      if path.isdir(self.dbFolder):
         self.gui.addMsg("Deleted folder " + self.dbFolder)
         shutil.rmtree(self.dbFolder)

      if self.modConfigPath != None and path.isdir(self.modConfigPath):
         self.gui.addMsg("Deleted folder " + self.modConfigPath)
         shutil.rmtree(self.modConfigPath)
         
      self.initDatabase()

   def scrub(self, _string):
      return ''.join( chr for chr in _string if (chr.isalnum() or chr == "+" or chr == "_" or chr == "-" or chr == "/"))

   def writeTestLog(self):
      with open("log.html", "w") as log:
         log.write("""<div class="time">00:00:00</div>""")
         log.write("""<div class="text">BBPARSER;String;Vanilla;this.logInfo("Hello, World!");</div>""")


         # log.write("""<div class="text">BBPARSER;ModSetting;MSU;logall;true;</div>""")
         # log.write("""<div class="text">BBPARSER;ModSetting;MSU;logall;false;</div>""")
         # log.write("""<div class="text">BBPARSER;ModSetting;MSU;logall;true;</div>""")
         # log.write("""<div class="text">BBPARSER;PerkBuild;PlanPerks;this.World.Perks.importPerkBuilds("124$perk.hold_out#1+perk.rotation#1+perk.bags_and_belts#1+perk.mastery.polearm#1+~");</div>""")
         # for x in range(100):
         #    log.write("<div class='text'>BBPARSER;Keybind;MSU;{idx};c+ctrl</div>".format(idx = x))

   def setDebug(self, _val):
      if(_val):
         if path.isdir("./mod_db_debug") == False:
            os.mkdir("./mod_db_debug")
         if path.isdir("./mod_config") == False:
            os.mkdir("./mod_config")
         self.modConfigPath = "./mod_config"
         self.logPath = "./log.html"
         self.dbFolder = "./mod_db_debug"
         self.Mods = {}
      else:
         if path.isdir("./mod_db_debug"):
            shutil.rmtree("./mod_db_debug")
         if path.isdir("./mod_config"):
            shutil.rmtree("./mod_config")
         self.dbFolder = "./mod_db"
         self.initDatabase()

      self.gui.updateButtons()
      self.gui.updateOutput()
      self.gui.updateStringVarText(gui.logPathVar, self.logPath)
      self.gui.updateStringVarText(gui.dataPathVar, self.modConfigPath)
     


# Handles the GUI element
class GUI:
   def __init__(self, _database):
      self.database = _database
      self.database.gui = self
      self.PendingOutput = []
      self.bannerImg = PhotoImage(file=resource_path("assets/banner.gif"))  
      self.bannerCanvas = Canvas(root, width = 792, height =82)
      self.bannerCanvas.create_image(0, 0, anchor="nw", image=self.bannerImg)
      self.bannerCanvas.grid(row=0, column=0, columnspan = 2)

      self.titleLabel = Label(root, text="BBParser")
      self.titleLabel.grid(row=1, column=0)
      self.dbNameLabel = Label(root, text="Database: " + self.database.databaseName)
      self.dbNameLabel.grid(row=1, column=1)

      self.dataPathVar = StringVar(root, "Browse to your game directory")
      self.dataPathLabel = Label(root, textvariable = self.dataPathVar)
      self.dataPathLabel.grid(row=3, column=0)
      self.dataPathButton =  Button(text="Browse", command=self.updateGameDirectory)
      self.dataPathButton.grid(row=3, column=1)
      
      self.logPathVar = StringVar(root, "Browse to your log.html directory (documents/Battle Brothers/)")
      self.logPathLabel = Label(root, textvariable = self.logPathVar)
      self.logPathLabel.grid(row=4, column=0)
      self.logPathButton =  Button(text="Browse", command=self.updateLogDirectory)
      self.logPathButton.grid(row=4, column=1)

      self.deleteSingleSettingLabel = Label(root, text = "delete all settings for a select mod folder.")
      self.deleteSingleSettingLabel.grid(row=6, column=0)
      self.deleteSingleModButton = Button(root, text="delete mod settings", command=self.deleteSingleMod, state="disabled")
      self.deleteSingleModButton.grid(row=6, column=1)

      self.deleteAllLabel = Label(root, text = "delete all settings to get a clean install")
      self.deleteAllLabel.grid(row=7, column=0)
      self.deleteAllButton = Button(root, text="delete all settings", command=self.deleteAllSettings, state="active")
      self.deleteAllButton.grid(row=7, column=1)

      self.runParseButton = Button(root, text = "Update settings", command=self.runFileParse, state="disabled")
      self.runParseButton.grid(row=8, column=0)

      self.runInputButton = Button(root, text="Execute current input", command=self.runInputParse, state="active")
      self.runInputButton.grid(row=8, column=1)

      self.clearInputButton = Button(root, text="Clear input", command=self.clearOutput, state="active")
      self.clearInputButton.grid(row=9, column=1)


      self.ResultEntry = Text(root)
      self.ResultEntry.grid(row=9, column = 0)
      self.updateStringVarText(self.dataPathVar, self.database.modConfigPath if self.database.modConfigPath != None else "Browse to your game directory")
      self.updateStringVarText(self.logPathVar, self.database.logPath if self.database.logPath != None else "Select your log.html file (documents/Battle Brothers/log.html)")
      self.updateButtons()

   def updateGameDirectory(self):
      directory = filedialog.askdirectory()
      if directory == None or len(directory.split("/")) < 2 or (DEBUGGING == False and directory.split("/")[-1] != "data"):
         self.addMsg("Bad Path! " + str(directory))
      else:
         self.database.updateGameDirectory(directory+"/mod_config")
         self.updateStringVarText(self.dataPathVar, self.database.modConfigPath)
         self.addMsg("Directory selected successfully! " + str(directory))
      self.updateButtons()
      self.updateOutput()
         
   def updateLogDirectory(self):
      directory = filedialog.askopenfile(mode ='r', filetypes =[('log.html', 'log.html')])
      if directory == None or directory.name.split("/")[-1] != "log.html":
         self.addMsg("Bad Path! " + str(directory))
      else:
         self.database.updateLogDirectory(directory.name)
         self.updateStringVarText(self.logPathVar, self.database.logPath)
         self.addMsg("log file selected successfully! " + directory.name)
      self.updateButtons()
      self.updateOutput()

   def updateStringVarText(self, _stringvar, _text):
      _stringvar.set(_text)

   def updateButtonStatus(self, _button, _bool):
      if _bool:
         _button.config(state = "active")
      else:
         _button.config(state = "disabled")

   def updateButtons(self):
      self.updateButtonStatus(self.runParseButton, self.database.isReadyToRun())
      self.updateButtonStatus(self.deleteSingleModButton, self.database.modConfigPath != None)
      # self.updateButtonStatus(self.deleteSingleSettingButton, self.database.modConfigPath != None)

   def resetStringVars(self):
      self.updateStringVarText(self.dataPathVar, "Browse to your game directory")
      self.updateStringVarText(self.logPathVar, "Select your log.html file (documents/Battle Brothers/log.html)")

   def runFileParse(self):
      self.clearOutput()
      self.addMsg("Currently parsing file!")
      self.runParseButton.configure(text = "Stop Updating", command= self.stopParse)
      self.database.clearLoopVars()
      self.database.parseLogInLoop()

   def stopParse(self):
      self.runParseButton.configure( text = "Update settings", command=self.runFileParse)
      self.database.StopLoop = True

   def runInputParse(self):
      self.addMsg("Trying to parse input")
      text = self.ResultEntry.get("1.0",END)
      self.database.parseLocalInput(text)

   def deleteAllSettings(self):
      answer = askyesno("delete all settings", "Are you sure? This will delete all files in your mod_config and the database.")
      if answer:
         self.clearOutput()
         self.resetStringVars()
         self.updateButtons()
         self.database.deleteAllSettings()
      self.updateOutput()

   def deleteSingleMod(self):
      win = Toplevel()
      win.wm_title("Delete mod")

      l = Label(win, text="Select mod or setting")
      l.grid(row=0, column=0)
      mods = self.database.Mods
      modList = []
      for mod, modObj in mods.items():
         modList.append(mod)
         for option, optionObj in modObj.Options.items():
            modList.append(mod + " : " + optionObj.commandType)

      OptionVar = StringVar(win)
      w = OptionMenu(win, OptionVar, None, *modList)
      w.grid(row=0, column=1)

      def removeSetting():
         setting = OptionVar.get()
         if(str(setting) != "None"): #if you select the empty first item it returns string "None" instead of None so I just check against that
            self.database.delete(setting)
         win.destroy()

      b = Button(win, text="Okay", command=removeSetting)
      b.grid(row=1, column=0)
      

   def addMsg(self, _text, _newline = True):
      if _newline:
         _text += "\n"
      
      self.PendingOutput.append(_text)

   def updateOutput(self):
      result = ""
      while len(self.PendingOutput) > 0:
         text = self.PendingOutput.pop(0)
         result += text
         printDebug(text)
      self.ResultEntry.insert(END, result)
      
   def clearOutput(self):
      self.ResultEntry.delete('1.0', END)
      self.PendingOutput = []


global DBNAME
DEBUGGING = False #can be enabled via writing and executing DEBUG, then parses local log and writes to local files

if(len(sys.argv) > 1):
   DBNAME = sys.argv[1]
else:
   DBNAME = 'mod_settings.db'

defaultDB = Database(DBNAME)

gui = GUI(defaultDB)



root.mainloop()