import os
from tkinter import filedialog
from tkinter import *
from bs4 import BeautifulSoup
from pathlib import Path
from bs4 import BeautifulSoup
from os import path
from string import Template
import sqlite3
from contextlib import closing
from contextlib import contextmanager
from tkinter.messagebox import askyesno
import shutil
import sys

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
      self.initDatabase()

   def initDatabase(self):
      with db_ops(self.database.databaseName) as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + self.dbkey + " (test text)")


   def scrub(self, table_name):
    return ''.join( chr for chr in table_name if chr.isalnum() )

   def handleAction(self, action):
      pass

   def writeToFile(self, _file, _fileObj):
      pass

#Base Type
class WriteString(Option):
   def __init__(self, _id, _modID, _database):
      super().__init__(_id, _modID, _database)
      self.toPrint = ""

   def handleAction(self, action):
      self.toPrint += action[2] +"\n"

   def writeToFile(self, _file, _fileObj):
      with open(_file + ".nut", 'a') as f:
         f.write(self.toPrint)
      _fileObj.TotalWritten.append(self.dbkey + " : " + self.toPrint)
      self.toPrint = ""

# example for more complicated parsing like creating a dict
class WriteModSetting(Option):
   def __init__(self,  _id, _modID, _database):
      super().__init__( _id, _modID, _database)
      self.Table = {}
      self.Template = """this.MSU.SettingsManager.updateSettings({"$modID", "$setting", $value)"""

   def initDatabase(self):
      key = self.scrub(self.modID + self.id)
      with db_ops(self.database.databaseName) as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + key + " (modID text, settingID text, value text)")
      self.dbkey = key


   def handleAction(self, action):
      modID = action[1]
      setting = action[2]
      value = action[3]
      with db_ops(self.database.databaseName) as cur:
         cur.execute("SELECT * FROM " + self.dbkey + " WHERE settingID = ?", (setting,))
         rows = cur.fetchall()
         if(len(rows) == 0):
            cur.execute("INSERT INTO " + self.dbkey + " VALUES (?, ?, ?)" , (modID, setting, value))
         else:
            cur.execute("UPDATE " + self.dbkey + " SET value = :value WHERE modID = :modID and settingID = :setting", {"value" : value, "modID" : modID, "setting" : setting })


   def writeToFile(self, _file, _fileObj):
      with db_ops(self.database.databaseName) as cur:
         cur.execute("SELECT * FROM " + self.dbkey)
         with open(_file + ".nut", 'w') as f:
            rows = cur.fetchall()
            for row in rows:
               temp = Template(self.Template)
               sub = temp.substitute(modID = row[0], setting = row[1], value = row[2])
               f.write(sub)
               _fileObj.TotalWritten.append(self.dbkey + " : " + sub)
      self.toPrint = ""



class ParseObject:
   def __init__(self, _database):
      self.TotalWritten = []
      self.Mods = {}
      self.Options = {
         "ModSetting" : WriteModSetting, 
         "Default" : WriteString
      }
      self.database = _database # could use that idk
      ResultEntry.delete('1.0', END)

   def parse(self):
      commands = self.getCommands()
      for command in commands:
         commandType = command[0]
         modName = command[1]
         if modName not in self.Mods:
            self.Mods[modName] = {
               "Options"  : {}
            }
         mod = self.Mods[modName]
         if (commandType in mod["Options"]) == False:
            if commandType not in self.Options:
               mod["Options"][commandType] = self.Options["Default"](commandType, modName, self.database)
            else:
               mod["Options"][commandType] = self.Options[commandType](commandType, modName, self.database)
         mod["Options"][commandType].handleAction(command)

   def getCommands(self):
      results = []
      with open(self.database.logpath + "/log.html") as fp:
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


# ------------------------------------------------ visuals -----------------------------------------

#just a namespace atm
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
            cur.execute("""UPDATE paths SET path = ? WHERE type = 'log'""", (self.gamepath,))
            cur.execute("""UPDATE paths SET path = ? WHERE type = 'data'""", (self.logpath,))
      else:
         runButton.config(state = "disabled")

   def UpdateText(self):
      parseobj = ParseObject(self)
      parseobj.parse()
      parseobj.write_files()

   def DeleteSettings(self):
      answer = askyesno("Delete all settings", "Are you sure? This will delete all files in your mod_config and the database.")
      if answer:
         os.remove(self.databaseName)
         ResultEntry.delete('1.0', END)
         if self.gamepath != None and path.isdir(self.gamepath+"/mod_config"):
            shutil.rmtree(self.gamepath+"/mod_config")
         self.initDatabase()
         textGamePath.config(text = "Browse to your game directory")
         textLogPath.config(text = "Browse to your log.html directory (documents/Battle Brothers/)")
      

global DBNAME
if(len(sys.argv) > 1):
   DBNAME = sys.argv[1]
else:
   DBNAME = 'mod_settings.db'

defaultDB = Database(DBNAME)



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

deleteButton = Button(root, text="Delete settings", command=defaultDB.DeleteSettings, state="active")
deleteButton.grid(row=5, column=1)

ResultEntry = Text(root)
ResultEntry.grid(row=6)

defaultDB.checkButtonStatus()






root.mainloop()