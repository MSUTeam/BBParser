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
import typing
from typing import Dict, List, Generator, Union
import traceback

printDebug = None

@contextmanager
def db_ops(db_name: str) -> Generator:
   conn = sqlite3.connect(db_name)
   cur = conn.cursor()
   yield cur
   conn.commit()
   conn.close()

def resource_path(relative_path: str) -> str:
   if hasattr(sys, '_MEIPASS'): 
      return os.path.join(sys._MEIPASS, relative_path) # type: ignore
   return os.path.join(os.path.abspath("."), relative_path) 

# The result of a command string extracted from the log or other
class CommandObject:
   @staticmethod
   def getCommandObj(_command):
      splitCommand = CommandObject.splitCommand(_command)
      if CommandObject.validateCommand(splitCommand):
         return CommandObject(splitCommand)

   @staticmethod
   def splitCommand(_command):
      return list(map(lambda string: string.replace("\@", "@"), re.findall("""(?<=@).*?[^\\\\](?=@)""", _command)))

   @staticmethod
   def validateCommand(_command : List[str]) -> bool:
      #_command = [self.scrub(entry) for entry in _command]
      if len(_command) < 3:
         print("Command {command} is not valid! Too few entries.".format(command = str(_command)))
         return False
      for entry in _command:
         if len(entry) == 0:
            print("Command {command} is not valid! Entry {entry} length is 0.".format(command = str(_command), entry = entry))
      return True

   def __init__(self, _commandList) -> None:
      self.commandType : str = _commandList[0]
      self.modID : str = _commandList[1]
      self.value : List[str] = _commandList[2:]


   # def scrub(self, _string : str) -> str:
   #    return ''.join( chr for chr in _string if (chr.isalnum() or chr == "+" or chr == "_" or chr == "-" or chr == "/" or chr == "@"))


class Mod:
   def __init__(self, _modID: str, _path: str, _dbPath: str) -> None:
      self.ModID = _modID
      self.ConfigPath = _path + "/" + self.ModID
      self.DBPath = _dbPath + self.ModID + ".db"
      self.Options: Dict[str, CommandOption] = {}
      self.guiOutput = []

   def handleCommand(self, _commandObj: CommandObject) -> None:
      commandOption = CommandOption.getCommandClass(_commandObj.commandType, self)
      if commandOption.commandType not in self.Options:
         self.Options[commandOption.commandType] = commandOption
      self.Options[commandOption.commandType].handleCommand(_commandObj)

   def initDatabase(self) -> None:
      pass

   def writeFiles(self) -> None:
      if path.isdir(self.ConfigPath) == False:
         os.mkdir(self.ConfigPath)
      for optionType, optionObj in self.Options.items():
         if optionObj.shouldWriteToFile():
            optionObj.writeToFile()
            for line in optionObj.getWriteResult():
               self.guiOutput.append(line)

   def getGuiOutput(self):
      result = self.guiOutput.copy()
      self.guiOutput.clear()
      return result

   def __str__ (self) -> str:
      result = 'Mod(ModID: {modid} | ConfigPath: {configpath} | DBPath: {dbpath})'.format(modid = self.ModID, configpath = self.ConfigPath, dbpath = self.DBPath)
      return result

# Base Class for a command option, some type of command that treats the passed data in a specific way
class CommandOption:
   @staticmethod
   def getCommandClass(_commandType: str, _mod: Mod):
      if _commandType == "ModSetting":
         return WriteModSetting(_commandType, _mod)
      elif _commandType == "Keybind":
         return WriteKeybind(_commandType, _mod)
      else:
         if (_commandType.find(":APPEND") != -1):
            _commandType = _commandType.split(":APPEND")[0]
            return WriteStringAppend(_commandType, _mod)
         else:
            return WriteString(_commandType, _mod)

   def __init__(self, _id: str, _mod: Mod) -> None:
      self.commandType = _id
      self.mod = _mod
      printDebug("Created new CommandOption obj: " + str(self))

   def returnWriteResultHeader(self, _result: str) -> str:
      return "\nMod {modID} wrote option {commandType}: {result}".format(modID = self.mod.ModID, commandType = self.commandType, result = _result)

   def returnFileHeader(self) -> str:
      return 'this.logInfo("{modID}::{commandType} is being executed");\n'.format(modID = self.mod.ModID, commandType = self.commandType)

   def validateCommand(self, _commandObj: CommandObject) -> bool:
      return True

   def handleCommand(self, _commandObj: CommandObject) -> None:
      pass

   def getWritePath(self) -> str:
      return path.join(self.mod.ConfigPath, self.commandType) + ".nut"

   def shouldWriteToFile(self) -> bool:
      return False

   # writes the mod_config files
   def writeToFile(self) -> None:
      pass

   # returns a list of str results from writeToFile to be printed to the GUI
   def getWriteResult(self) -> List[str]:
      return []

   def __str__ (self) -> str:
      return '{type}(commandType: {commandType} | Mod: {modID} | dbTableKey: {dbTableKey})'.format(type = self.__class__.__name__, commandType = self.commandType, modID = self.mod.ModID, dbTableKey = self.mod.DBPath)

#Simple type that doesn't write to the DB
class WriteString(CommandOption):
   def __init__(self, _commandType: str, _mod: Mod) -> None:
      super().__init__(_commandType, _mod)
      self.toPrint = ""

   def handleCommand(self, _commandObj: CommandObject) -> None:
      self.toPrint = self.getStringToPrint(_commandObj)

   def getStringToPrint(self, _commandObj: CommandObject) -> str:
      result = "\n"
      for entry in _commandObj.value:
         result += "\n" + entry
      return result

   def shouldWriteToFile(self) -> bool:
      return self.toPrint != ""

   def writeToFile(self) -> None:
      with open(self.getWritePath(), 'w') as f:
         f.write(self.returnFileHeader())
         f.write(self.toPrint)

   def getWriteResult(self) -> List[str]:
      toPrint = [self.returnWriteResultHeader(self.toPrint)]
      self.toPrint = ""
      return toPrint

class WriteStringAppend(WriteString):
   def handleCommand(self, _commandObj: CommandObject) -> None:
      self.toPrint += self.getStringToPrint(_commandObj)

   def writeToFile(self) -> None:
      fileExists = path.isfile(self.getWritePath())
      with open(self.getWritePath(), 'a') as f:
         if fileExists == False:
            f.write(self.returnFileHeader())
         f.write(self.toPrint)

#Type that writes to DB and prints all rows
class WriteDatabase(CommandOption):
   def __init__(self,  _commandType: str, _mod: Mod, _template: str, _templateArguments: List[str]) -> None:
      super().__init__( _commandType, _mod)
      self.Template = _template 
      self.TemplateArguments = _templateArguments
      self.initDatabase()
      self.changedSinceLastUpdate = True
      self.toLog: List[str] = [];

   def getTemplate(self, _modID: str, _settingID: str, _value: str) -> str:
      argmap = {}
      argmap["modID"] = _modID
      argmap["settingID"] = _settingID
      argmap["value"] = _value
      temp = Template(self.Template)
      sub = temp.substitute(argmap)
      return sub

   def initDatabase(self) -> None:
      columns = " ("
      for idx, colName in enumerate(self.TemplateArguments):
         columns += colName + " text"
         if idx != len(self.TemplateArguments) -1:
            columns += ", "
      columns += ")"
      result = self.commandType + columns
      with db_ops(self.mod.DBPath) as cur:
         cur.execute('CREATE TABLE IF NOT EXISTS {}'.format(result.replace('"', '""')))

   def shouldWriteToFile(self) -> bool:
      # only write to file if it had updates in last parsing loop
      return self.changedSinceLastUpdate

   def writeToFile(self) -> None:
      with db_ops(self.mod.DBPath) as cur:
         cur.execute('SELECT * FROM "{}"'.format(self.commandType.replace('"', '""')))
         with open(self.getWritePath(), 'w') as f:
            f.write(self.returnFileHeader())
            rows = cur.fetchall()
            for row in rows:
               f.write(self.getTemplate(row[0], row[1], row[2]))


   def getWriteResult(self) -> List[str]:
      self.changedSinceLastUpdate = False
      toPrint = []
      for line in self.toLog:
         toPrint.append(self.returnWriteResultHeader(line))
      self.toLog = []
      return toPrint

   def handleCommand(self, _commandObj: CommandObject) -> None:
      self.changedSinceLastUpdate = True
      with db_ops(self.mod.DBPath) as cur:
         cur.execute('SELECT * FROM "{}" WHERE settingID = ?'.format(self.commandType.replace('"', '""')), (_commandObj.value[0],))
         rows = cur.fetchall()
         if(len(rows) == 0):
            cur.execute('INSERT INTO "{}" VALUES (?, ?, ?)'.format(self.commandType.replace('"', '""')), (_commandObj.modID, _commandObj.value[0], _commandObj.value[1]))
         else:
            cur.execute('UPDATE "{}" SET value = ? WHERE modID = ? and settingID = ?'.format(self.commandType.replace('"', '""')), (_commandObj.value[1], _commandObj.modID, _commandObj.value[0]))
         self.toLog.append(self.getTemplate(_commandObj.modID, _commandObj.value[0], _commandObj.value[1]))

# Ingame mod settings menu
class WriteModSetting(WriteDatabase):
   def __init__(self,  _commandType, _mod: Mod) -> None:
      super().__init__( _commandType, _mod, """this.MSU.System.ModSettings.setSettingFromPersistence("$modID", "$settingID", $value);\n""", ["modID", "settingID", "value"])


# Custom keybind handler settings menu option
class WriteKeybind(WriteDatabase):
   def __init__(self,  _commandType, _mod: Mod) -> None:
      super().__init__( _commandType, _mod, """this.MSU.System.Keybinds.updateFromPersistence("$modID", "$settingID", $value);\n""", ["modID", "settingID", "value"])


class LoopDone(Exception):
   pass

#manages all the CommandOptions to categorise them into Mods, parses the commands and outputs to the files
# Handles the Database connection

class Database:
   def __init__(self, _bbparser) -> None:
      self.bbparser = _bbparser
      self.mainFolderPath = "./" + self.bbparser.DBNAME
      self.modsFolderPath = self.mainFolderPath + "/mods/"
      self.pathsDatabasePath = self.mainFolderPath + "/paths_db.db"
      self.modConfigPath : str = ""
      self.logPath : str = ""
      self.Mods : Dict[str, Mod] = {}
      
      self.guiOutput : List[str] = []
      self.PreviousReadIndex = 0
      self.LastUpdateTime : float = 0.0
      self.LastBootTime : List[float] = [0, 0, 0]

      self.initMainFolder()
      self.initDatabase()
      self.getExistingModFiles()

   def initDatabase(self) -> None:
      with db_ops(self.pathsDatabasePath) as cur:
         cur.execute('SELECT count(*) from sqlite_master WHERE type="table" AND name="paths"')
         database = cur.fetchone()
         if(database[0] == 0):
            cur.execute('CREATE TABLE paths (type text, path text)')
            cur.execute('INSERT INTO paths VALUES ("data", Null)')
            cur.execute('INSERT INTO paths VALUES ("log", Null)')
            return

         cur.execute('SELECT path FROM paths WHERE type="data"')
         gamedir = cur.fetchone()
         if(gamedir[0] != None):
            self.modConfigPath = gamedir[0]   

         # Create log.html path database entry
         cur.execute('SELECT path FROM paths WHERE type="log"')
         logdir = cur.fetchone()
         if(logdir[0] != None):
            self.logPath = logdir[0]            

   def initMainFolder(self) -> None:
      if path.isdir(self.mainFolderPath) == False:
         os.mkdir(self.mainFolderPath)
      if path.isdir(self.modsFolderPath) == False:
         os.mkdir(self.modsFolderPath)

   def getExistingModFiles(self) -> None:
      if self.modConfigPath == "":
         return
      idx = 0
      for (dirpath, dirnames, filenames) in os.walk(self.modConfigPath):
         if (idx == 0):
            for name in dirnames:
               if name not in self.Mods:
                  self.Mods[name] = Mod(name, dirpath, self.modsFolderPath)
                  printDebug("Added mod: " + str(self.Mods[name]))
         else:
            modname = dirpath.split("\\")[-1]
            for filename in filenames:
               filename = filename.split(".")[0]
               if filename not in self.Mods[modname].Options:
                  self.Mods[modname].Options[filename] = CommandOption.getCommandClass(filename, self.Mods[modname])
         idx += 1

   def updateGameDirectory(self, _path: str) -> None:
      self.modConfigPath = _path
      with db_ops(self.pathsDatabasePath) as cur:
         cur.execute("""UPDATE paths SET path = ? WHERE type = 'data'""", (self.modConfigPath,))
      
   def updateLogDirectory(self, _path: str) -> None:
      self.logPath = _path
      with db_ops(self.pathsDatabasePath) as cur:
         cur.execute("""UPDATE paths SET path = ? WHERE type = 'log'""", (self.logPath,))

   
   def isReadyToRun(self) -> bool:
      return self.modConfigPath != "" and self.logPath != ""

   def loopOnce(self):
      currentTimeFromLog = os.path.getmtime(self.logPath)
      if self.LastUpdateTime != currentTimeFromLog:
         self.LastUpdateTime = currentTimeFromLog
         
         if self.isNewBoot():
            self.setBootTime()
            self.PreviousReadIndex = 0
        
         self.parseGameLog()
         self.writeFiles()

   def getBootTime(self) -> List[float]:
      # gets time info of first entry ín the log
      with open(self.logPath) as fp:  
         time = re.search('(?:<div class="time">)(\d\d:\d\d:\d\d)(?:<\/div>)', fp.readline())
         # local input
         if time == None:
            return [0, 0, 0]
         return [float(num) for num in time.group(1).split(":")]

   def setBootTime(self) -> None:
      self.LastBootTime = self.getBootTime()
   
   def isNewBoot(self) -> bool:
      # See if the game has been restarted and we need to index from 0 again
      if self.LastBootTime == 0.0: 
         return True
      currentBootTime = self.getBootTime()
      for num1, num2 in zip(currentBootTime, self.LastBootTime):
         if num1 > num2:
            return True
      return False

   def finishLoop(self):
      self.clearLoopVars()

   def clearLoopVars(self) -> None:
      self.guiOutput = []
      self.LastBootTime = [0, 0, 0]
      self.LastUpdateTime = 0.0
      self.PreviousReadIndex = 0

   def parseGameLog(self) -> None:
      commands = self.getCommandsFromLog()
      for command in commands:
         commandObj = CommandObject.getCommandObj(command)
         self.PreviousReadIndex += 1
         if commandObj == None:
            continue
         modID = commandObj.modID
         if modID not in self.Mods:
            self.Mods[modID] = Mod(modID, self.modConfigPath, self.modsFolderPath)
         self.Mods[modID].handleCommand(commandObj)
         
   def getCommandsFromLog(self) -> List[List[str]]:
      with open(self.logPath) as fp: 
         regexResult = re.findall('(?:<div class="text">@BBPARSER)(.+?)(?=<\/div>)', fp.readline())
         return regexResult[self.PreviousReadIndex:]

   def writeFiles(self) -> None:
      if path.isdir(self.modConfigPath) == False:
         os.mkdir(self.modConfigPath)
      for modID, mod in self.Mods.items():
         mod.writeFiles()
         self.guiOutput.extend(mod.getGuiOutput())

   def getGuiOutput(self):
      result = self.guiOutput.copy()
      self.guiOutput.clear()
      return result

   #this can be expanded to parse things further
   def writeInputLog(self, _input : str) -> None:
      with open("local_log.html", "w") as log:
         for line in _input.split(";"):
            log.write("""<div class="text">BBPARSER;Global;MSU;""" + line.rstrip() + """</div>""")

   def deleteMod(self, _modID : str)  -> None:
      mod = self.Mods[_modID]
      directory = mod.ConfigPath
      db_directory = mod.DBPath
      try: 
         shutil.rmtree(directory)
         self.guiOutput.append("Deleted folder: " + directory)
      except Exception as e:
         self.guiOutput.append("Could not delete folder " + str(directory) + " : " + str(e))
        
      self.removeDB(db_directory)
      del self.Mods[_modID]

   def deleteOptionFromMod(self, _modID : str, _commandType : str)  -> None:
      mod = self.Mods[_modID]
      directory = mod.ConfigPath + "/" + _commandType +".nut"
      db_directory = mod.DBPath
      try: 
         os.remove(directory)
         self.guiOutput.append("Deleted folder: " + directory)
      except Exception as e:
         self.guiOutput.append("Could not delete folder " + directory + " : " + str(e))

      self.removeFromDB(db_directory, _commandType)
      del mod.Options[_commandType]


   def removeDB(self, _path : str) -> None:
      if path.isfile(_path):
         try:
            os.remove(_path)
            self.guiOutput.append("Deleted database " + _path)
         except:
            self.guiOutput.append("Could not delete database " + _path)
         

   def removeFromDB(self, _path : str, _commandType : str) -> None:
      if path.isfile(_path):
         try:
            with db_ops(_path) as cur:
               cur.execute("DROP TABLE IF EXISTS " + _commandType)
            self.guiOutput.append("Deleted data " + _commandType + " from database " + _path)
         except:
            self.guiOutput.append("Could not delete data " + _commandType + " from database " + _path)      

   def writeTestLog(self) -> None:
      with open("log.html", "w") as log:
         log.write("""<div class="time">00:00:00</div>""")
         log.write("""<div class="text">BBPARSER;String;Vanilla;this.logInfo("Hello, World!");</div>""")


         # log.write("""<div class="text">BBPARSER;ModSetting;MSU;logall;true;</div>""")
         # log.write("""<div class="text">BBPARSER;ModSetting;MSU;logall;false;</div>""")
         # log.write("""<div class="text">BBPARSER;ModSetting;MSU;logall;true;</div>""")
         # log.write("""<div class="text">BBPARSER;PerkBuild;PlanPerks;this.World.Perks.importPerkBuilds("124$perk.hold_out#1+perk.rotation#1+perk.bags_and_belts#1+perk.mastery.polearm#1+~");</div>""")
         # for x in range(100):
         #    log.write("<div class='text'>BBPARSER;Keybind;MSU;{idx};c+ctrl</div>".format(idx = x))
     


# Handles the GUI element
class GUI:
   def __init__(self, _bbparser) -> None:
      self.bbparser = _bbparser
      self.root = Tk()
      self.root.title("BBParser")
      self.root.iconphoto(False, PhotoImage(file=resource_path("assets\\icon.png")))
      self.PendingOutput : List[str] = []
      self.bannerImg = PhotoImage(file=resource_path("assets\\banner.gif"))  
      self.bannerCanvas = Canvas(self.root, width = 792, height = 82)
      self.bannerCanvas.create_image(0, 0, anchor="nw", image=self.bannerImg)
      self.bannerCanvas.grid(row=0, column=0, columnspan = 2)

      self.titleLabel = Label(self.root, text="BBParser")
      self.titleLabel.grid(row=1, column=0)
      #self.dbNameLabel = Label(self.root, text="Database: " + database.pathsDatabasePath)
      self.dbNameLabel = Label(self.root, text="Database: ")
      self.dbNameLabel.grid(row=1, column=1)

      self.dataPathVarDefault = "Browse to your game directory (./Battle Brothers/data)"
      self.dataPathVar = StringVar(self.root, self.dataPathVarDefault)
      self.dataPathLabel = Label(self.root, textvariable = self.dataPathVar)
      self.dataPathLabel.grid(row=3, column=0)
      self.dataPathButton =  Button(text="Browse", command=self.bbparser.updateGameDirectory)
      self.dataPathButton.grid(row=3, column=1)
      
      self.logPathVarDefault = "Browse to your log.html directory (documents/Battle Brothers/)"
      self.logPathVar = StringVar(self.root, self.logPathVarDefault)
      self.logPathLabel = Label(self.root, textvariable = self.logPathVar)
      self.logPathLabel.grid(row=4, column=0)
      self.logPathButton =  Button(text="Browse", command=self.bbparser.updateLogDirectory)
      self.logPathButton.grid(row=4, column=1)

      self.deleteSingleSettingLabel = Label(self.root, text = "Delete files for a select mod.")
      self.deleteSingleSettingLabel.grid(row=6, column=0)
      self.deleteSingleModButton = Button(self.root, text="Delete mod files", command=self.bbparser.onDeleteButtonPressed, state="disabled")
      self.deleteSingleModButton.grid(row=6, column=1)

      self.deleteAllLabel = Label(self.root, text = "Delete all files to get a clean install")
      self.deleteAllLabel.grid(row=7, column=0)
      self.deleteAllButton = Button(self.root, text="Delete all files", command= self.bbparser.onDeleteAllButtonPressed, state="active")
      self.deleteAllButton.grid(row=7, column=1)

      self.runParseButton = Button(self.root, text = "Update settings", command=self.bbparser.onRunFromParseButtonPressed, state="disabled")
      self.runParseButton.grid(row=8, column=0)

      self.runInputButton = Button(self.root, text="Execute current input", command=self.bbparser.onRunFromInputButtonPressed, state="active")
      self.runInputButton.grid(row=8, column=1)

      self.clearInputButton = Button(self.root, text="Clear input", command = self.clearOutput, state="active")
      self.clearInputButton.grid(row=9, column=1)


      self.ResultEntry = Text(self.root)
      self.ResultEntry.grid(row=9, column = 0)

   def updateStringVarText(self, _stringvar : StringVar, _text : str) -> None:
      _stringvar.set(_text)

   def resetStringVars(self) -> None:
      self.updateStringVarText(self.dataPathVar, self.dataPathVarDefault)
      self.updateStringVarText(self.logPathVar, self.logPathVarDefault)

   def updateButtonStatus(self, _button : Button, _bool : bool) -> None:
      if _bool:
         _button.config(state = "active")
      else:
         _button.config(state = "disabled")

   def addMsg(self, _text : str, _newline : bool = True) -> None:
      if _newline:
         _text += "\n"
      self.PendingOutput.append(_text)

   def updateOutput(self) -> None:
      result = ""
      while len(self.PendingOutput) > 0:
         text = self.PendingOutput.pop(0)
         result += text
         printDebug(text)
      self.ResultEntry.insert(END, result)
      
   def clearOutput(self) -> None:
      self.ResultEntry.delete('1.0', END)
      self.PendingOutput = []

class BBParser:
   def __init__(self):
      self.DEBUGGING = False
      self.DBNAME = "default"
      self.IsLooping = False
      if len(sys.argv) > 1:
         self.DBNAME = sys.argv[1]
      global printDebug
      printDebug = self.printDebug
      self.setupDataBase()
      self.setupGUI()

   def setupDataBase(self):
      self.database = Database(self)

   def setupGUI(self):
      self.gui = GUI(self)
      self.gui.updateStringVarText(self.gui.dataPathVar, "Data Folder Path: {dataPath}".format(dataPath = self.database.modConfigPath) if self.database.modConfigPath != "" else self.gui.dataPathVarDefault)
      self.gui.updateStringVarText(self.gui.logPathVar, "log.html Path: {logPath}".format(logPath = self.database.logPath) if self.database.logPath != "" else self.gui.logPathVarDefault)
      self.updateButtons()

   def updateGameDirectory(self) -> None:
      directory = filedialog.askdirectory()
      if directory == None or len(directory.split("/")) < 2 or (self.DEBUGGING == False and directory.split("/")[-1] != "data"):
         self.gui.addMsg("Bad Path! " + str(directory))
      else:
         self.database.updateGameDirectory(directory + "/mod_config")
         self.gui.updateStringVarText(self.gui.dataPathVar, "Data Folder Path: {dataPath}".format(dataPath = self.database.modConfigPath))
         self.gui.addMsg("Directory selected successfully! " + str(directory))
      self.updateGUI()
         
   def updateLogDirectory(self) -> None:
      directory = filedialog.askopenfile(mode ='r', filetypes =[('log.html', 'log.html')])
      if directory == None or directory.name.split("/")[-1] != "log.html": # type: ignore
         self.gui.addMsg("Bad Path! " + str(directory))
      else:
         self.database.updateLogDirectory(directory.name) # type: ignore
         self.gui.updateStringVarText(self.gui.logPathVar, "log.html Path: {logPath}".format(logPath = self.database.logPath))
         self.gui.addMsg("log.html selected successfully! " + directory.name) # type: ignore
      self.updateGUI()

   def updateGUI(self):
      self.gui.updateOutput()
      self.updateButtons()
      
   def updateButtons(self) -> None:
      self.gui.updateButtonStatus(self.gui.runParseButton, self.database.isReadyToRun())
      self.gui.updateButtonStatus(self.gui.deleteSingleModButton, self.database.modConfigPath != None and self.IsLooping == False and len(self.database.Mods) > 0)
      self.gui.updateButtonStatus(self.gui.deleteAllButton, self.IsLooping == False)
      if self.IsLooping:
         self.gui.runParseButton.configure(text = "Stop Parsing", command = self.onRunFromParseButtonPressed)
      else:
         self.gui.runParseButton.configure( text = "Parse log.html", command = self.onRunFromParseButtonPressed)
      # self.updateButtonStatus(self.deleteSingleSettingButton, database.modConfigPath != None)

   def onDeleteButtonPressed(self) -> None:
      win = Toplevel()
      win.wm_title("Delete mod files")

      l = Label(win, text="Select mod or file")
      l.grid(row=0, column=0)
      mods = self.database.Mods
      modList = []
      for mod, modObj in mods.items():
         modList.append(mod)
         for option, optionObj in modObj.Options.items():
            combinedString = mod + " : " + optionObj.commandType
            modList.append(combinedString)

      OptionVar = StringVar(win)
      w = OptionMenu(win, OptionVar, *modList)
      w.grid(row=0, column=1)

      def removeSetting():
         setting = OptionVar.get()
         if(str(setting) != "None"): #if you select the empty first item it returns string "None" instead of None so I just check against that
            self.deleteFromMenu(setting)
         win.destroy()

      b = Button(win, text="Okay", command = removeSetting)
      b.grid(row=1, column=0)

   def onDeleteAllButtonPressed(self) -> None:
      answer = askyesno("delete all settings", "Are you sure? This will delete all files in your mod_config and the database.")
      if answer:
         self.stopParse()
         os.remove(self.database.pathsDatabasePath)
         if path.isdir(self.database.modsFolderPath):
            self.gui.addMsg("Deleted folder " + self.database.modsFolderPath)
            shutil.rmtree(self.database.modsFolderPath)

         if self.database.modConfigPath != None and path.isdir(self.database.modConfigPath):
            self.gui.addMsg("Deleted folder " + self.database.modConfigPath)
            shutil.rmtree(self.database.modConfigPath)
         self.setupDataBase()
         self.updateGUI()

   def deleteFromMenu(self, _arg : str) -> None:
      if(_arg == ""):
         return
      result = _arg.split(":")
      if(len(result) == 1):
         self.database.deleteMod(result[0])

      elif(len(result) == 2):
         self.database.deleteOptionFromMod(result[0].rstrip(), result[1].lstrip())

      self.printDatabaseOutput()

   def onRunFromParseButtonPressed(self):
      if self.IsLooping:
         self.stopParse()
      else:
         self.runFileParse()

   def start(self):
      self.runIfReady()
      self.gui.root.mainloop()

   def runIfReady(self) -> None:
      if(self.database.isReadyToRun()):
         self.gui.root.iconify()
         self.runFileParse()

   def runFileParse(self) -> None:
      self.gui.clearOutput()
      self.gui.addMsg("Currently parsing file!")
      self.IsLooping = True
      self.updateGUI()
      self.database.clearLoopVars()
      self.parseLogInLoop()

   def stopParse(self) -> None:
      if self.IsLooping:
         self.IsLooping = False
         self.gui.addMsg("Stopped Parsing!")
         self.updateGUI()

   def onRunFromInputButtonPressed(self) -> None:
      self.gui.addMsg("Trying to parse input")
      text = self.gui.ResultEntry.get("1.0", END)
      self.parseLocalInput(text)

   def parseLogInLoop(self) -> None:
      #main loop, uses a try - else structure with root.after timeouts
      try:
         if self.IsLooping == False:
            raise LoopDone
         self.database.loopOnce()
         self.printDatabaseOutput()

      except LoopDone as e:
         self.database.finishLoop()
         self.IsLooping = False
         if self.DEBUGGING:
            os.remove("./log.html")

      except Exception as e:
         print("BBParser encountered an error: " +  str(e))
         print(traceback.format_exc())

      except IOError as e:
         self.gui.addMsg("Could not open log.html!")
         self.gui.updateOutput()
         if self.DEBUGGING:
            os.remove("./log.html")  

      else: 
         self.gui.root.after(1000, self.parseLogInLoop)

   def parseLocalInput(self, _input : str) -> None:
      if _input.rstrip() == "DEBUG":
         
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
         self.database.writeInputLog(_input)
         oldPath = self.database.logPath
         self.database.logPath = "./local_log.html"
         self.database.loopOnce()
         os.remove(self.database.logPath)
         self.database.logPath = oldPath

   def printDatabaseOutput(self):
      for msg in self.database.getGuiOutput():
         self.gui.addMsg(msg)
      self.updateGUI()

   def printDebug(self, _text: str) -> None:
      if self.DEBUGGING:
         print(_text)

   #not functional atm
   def setDebug(self, _val : bool) -> None:
      if(_val):
         self.DEBUGGING = True
         if path.isdir("./mod_db_debug") == False:
            os.mkdir("./mod_db_debug")
         if path.isdir("./mod_config") == False:
            os.mkdir("./mod_config")
         self.database.modConfigPath = "./mod_config"
         self.database.logPath = "./log.html"
         self.database.mainFolderPath = "debug"
         self.database.Mods = {}
      else:
         self.DEBUGGING = False
         if path.isdir("./mod_db_debug"):
            shutil.rmtree("./mod_db_debug")
         if path.isdir("./mod_config"):
            shutil.rmtree("./mod_config")
         self.database.dbFolder = "./mod_db"
         self.database.initDatabase()

      self.updateGUI()
      self.gui.updateStringVarText(self.gui.logPathVar, self.database.logPath) # type: ignore
      self.gui.updateStringVarText(self.gui.dataPathVar, self.database.modConfigPath) # type: ignore

bbparser = BBParser()
bbparser.start()
