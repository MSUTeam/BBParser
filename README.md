# BBParser
An application for parsing `log.html` of Battle Brothers, extracting data and writing the results to the data folder.

To edit the file, set up an Anaconda instance with Beautiful Soup 4

To turn it into an exe, add pyinstaller to your Anaconda instance then navigate to the script directory and run 

pyinstaller --onefile BBReader.py

To enable debug and write to local files, write DEBUG and execute input. To disable, write !DEBUG.

To write a PARSEME command that appends to the file instead of overwriting the content, add `:APPEND` after the command ID. Example: `PARSEME;mod_plan_perks;PerkBuild:APPEND;[payload];`. ":APPEND" will be removed from the ID.
