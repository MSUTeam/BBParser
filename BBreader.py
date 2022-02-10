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

@contextmanager
def db_ops(db_name):
   conn = sqlite3.connect(db_name)
   cur = conn.cursor()
   yield cur
   conn.commit()
   conn.close()

root = Tk()


global GAMEPATH
global LOGPATH
GAMEFOUND = False
LOGFOUND = False


# Base Class, some type of command that treats the passed data in a specific way
class Option:
   def __init__(self, _id, _modID, _database):
      self.id = _id
      self.modID = _modID
      self.database = _database
      self.dbkey = self.scrub(self.modID + self.id)
      self.initDatabase()

   def initDatabase(self):
      with db_ops('mod_settings.db') as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + self.dbkey + " (test text)")


   def scrub(self, table_name):
    return ''.join( chr for chr in table_name if chr.isalnum() )

   def handleAction(self, action):
      pass

   def writeToFile(self, _file, _path, _fileObj):
      pass

#Base Type
class WriteString(Option):
   def __init__(self, _id, _modID, _database):
      super().__init__(_id, _modID, _database)
      self.toPrint = ""

   def handleAction(self, action):
      self.toPrint += action[2] +"\n"

   def writeToFile(self, _file, _path, _fileObj):
      _file.write(self.toPrint)
      #print(self.id  + " for " + self.modID + " wrote " + self.toPrint)
      _fileObj.TotalWritten.append(self.toPrint)
      self.toPrint = ""

# example for more complicated parsing like creating a dict
class WriteModSetting(Option):
   def __init__(self,  _id, _modID, _database):
      super().__init__( _id, _modID, _database)
      self.Table = {}
      self.Template = """this.MSU.SettingsManager.updateSettings({"$modID", "$setting", $value)"""

   def initDatabase(self):
      key = self.scrub(self.modID + self.id)
      with db_ops('mod_settings.db') as cur:
         cur.execute("CREATE TABLE IF NOT EXISTS " + key + " (modID text, settingID text, value text)")
      self.DBKey = key


   def handleAction(self, action):
      modID = action[0]
      setting = action[1]
      value = action[2]
      with db_ops('mod_settings.db') as cur:
         cur.execute("SELECT * FROM " + self.DBKey + " WHERE settingID = ?", (setting,))
         rows = cur.fetchall()
         if(len(rows) == 0):
            print("INSERT?")
            cur.execute("INSERT INTO " + self.DBKey + " VALUES (?, ?, ?)" , (modID, setting, value))
         else:
            print("UPDATE?")
            cur.execute("UPDATE " + self.DBKey + " SET value = :value WHERE modID = :modID and settingID = :setting", {"value" : value, "modID" : modID, "setting" : setting })



      # if modID not in self.Table:
      #    self.Table[modID] = {}
      # if setting not in self.Table[modID]:
      #    self.Table[modID][setting] = None
      # self.Table[modID][setting] = value


      # for modID in self.Table:
      #    for setting in self.Table[modID]:
      #       temp = Template(self.Template)
      #       sub = temp.substitute(modID = modID, setting = setting, value = self.Table[modID][setting])
      #       self.toPrint += sub
      # super().writeToFile(_file)



class ParseObject:
   def __init__(self):
      self.TotalWritten = []
      self.Mods = {}
      self.Options = {
         "ModSetting" : WriteModSetting, 
         "Default" : WriteString
      }
      self.connection = None # could use that idk
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
               mod["Options"][commandType] = self.Options["Default"](commandType, modName, self.connection)
            else:
               mod["Options"][commandType] = self.Options[commandType](commandType, modName, self.connection)
         mod["Options"][commandType].handleAction(command)

   def getCommands(self):
      results = []
      with open(LOGPATH+"/log.html") as fp:
         soup = BeautifulSoup(fp, "html.parser")
         logInfoArray = soup.findAll(class_ = "text")
         for entry in logInfoArray:
            contents = entry.contents[0].split(";")
            if contents[0] == "PARSEME":
               results.append(contents[1:])
      return results


   def write_files(self):
      modConfigPath = GAMEPATH + "/mod_config"
      if path.isdir(modConfigPath) == False:
            os.mkdir(modConfigPath)

      for mod, modContents in self.Mods.items():
         modPath = path.join(modConfigPath, mod)
         if path.isdir(modPath) == False:
            os.mkdir(modPath)
         for option, optionContents in modContents.items():
            for optionType, optionClass in optionContents.items():
               typePath = path.join(modPath, optionType)
               with open(typePath + ".nut", 'a') as f:
                  optionClass.writeToFile(f, typePath + ".nut", self)
      
      ResultEntry.insert(END, self.TotalWritten)


# ------------------------------------------------ visuals -----------------------------------------

class Database:
   def initDatabase(_dbID):
      global LOGFOUND
      global GAMEFOUND
      with db_ops(_dbID) as cur:
         cur.execute('CREATE TABLE IF NOT EXISTS paths (type text, path text)')
         cur.execute('SELECT path FROM paths WHERE type="data"')
         global GAMEPATH
         GAMEPATH = cur.fetchone()
         if(GAMEPATH != None):
            GAMEPATH = GAMEPATH[0]
            GAMEFOUND = True
         else:
            cur.execute('INSERT INTO paths VALUES ("data", Null)')


         cur.execute('SELECT path FROM paths WHERE type="log"')
         global LOGPATH
         LOGPATH = cur.fetchone()
         if(LOGPATH != None):
            LOGPATH = LOGPATH[0]
            LOGFOUND = True
         else:
            cur.execute('INSERT INTO paths VALUES ("log", Null)')



def UpdateGameDirectory():
   global GAMEFOUND
   global GAMEPATH
   GAMEPATH = filedialog.askdirectory()
   if GAMEPATH.split("/")[-1] != "data":
      GAMEPATH = "Bad Directory!"
      textGamePath.config(text = GAMEPATH)
      GAMEFOUND = False
   else:
      GAMEFOUND = True
      textGamePath.config(text = GAMEPATH)
   checkButton()
   

def UpdateLogDirectory():
   global LOGFOUND
   global LOGPATH
   LOGPATH = filedialog.askdirectory()
   if "log.html" not in os.listdir(LOGPATH):
      LOGPATH = "Bad Directory!"
      textGamePath.config(text = LOGPATH)
      LOGFOUND = False
   else:
      LOGFOUND = True
      textLogPath.config(text = LOGPATH)
   checkButton()
   
def isButtonValid():
   return LOGFOUND and GAMEFOUND

def checkButton():
   if isButtonValid():
      with db_ops('mod_settings.db') as cur:
         myButton.config(state = "normal")
         cur.execute("""UPDATE paths SET path = ? WHERE type = 'log'""", (LOGPATH,))
         cur.execute("""UPDATE paths SET path = ? WHERE type = 'data'""", (GAMEPATH,))

   else:
      myButton.config(state = "disabled")



def UpdateText():
   parseobj = ParseObject()
   parseobj.parse()
   parseobj.write_files()



Database.initDatabase('mod_settings.db')



textHeading = Label(root, text="Battle Brothers Reader")
textHeading.grid(row=0, column=0)
textGamePath = Label(root, text = GAMEPATH if GAMEPATH != None else "Browse to your game directory")
textGamePath.grid(row=3, column=0)
buttonDirectory =  Button(text="Browse", command=UpdateGameDirectory)
buttonDirectory.grid(row=3, column=1)
textLogPath = Label(root, text=LOGPATH if LOGPATH != None else "Browse to your log.html directory (documents/Battle Brothers/)")
textLogPath.grid(row=4, column=0)
buttonDirectory =  Button(text="Browse", command=UpdateLogDirectory)
buttonDirectory.grid(row=4, column=1)

myButton = Button(root, text="Update settings", command=UpdateText, state="disabled")
myButton.grid(row=5, column=0)
ResultEntry = Text(root)
ResultEntry.grid(row=6)

checkButton()




root.mainloop()