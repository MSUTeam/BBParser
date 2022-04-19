# BBParser
A python application for parsing `log.html` of Battle Brothers, extracting data and writing the results to the data folder.\
It is primarly used in conjunction with the [MSU mod](https://github.com/MSUTeam/mod_MSU/wiki/Persistent-Data).

To turn it into an exe, use pyinstaller. Either add it to your editor, or install it with `pip install pyinstaller`. Navigate to the script directory and run 
`build.ps1` or `build.bat`.

Currently, the program accepts strings of the following format:
```squirrel
@BBPARSER@_fileID@_modID@_value0@_value1@...
// '@' is the separator between individual statements and at the beginning and the end of the command.
// To escape an '@', use '\@'
// BBPARSER must be present as the first entry of the string
// _fileID refers to the setting that is supposed to be executed
// Refer to the wiki for a list of settings
// _modID refers to the modhooks/MSU ID of the mod that writes the parse statement
// _value is an arbitrary amount of payload arguments
```
Examples:

```@BBPARSER@ModSetting@mod_msu@GreetingEnumSetting@GoodBye@```

This will set the value of the setting "GreetingEnumSetting" of mod_msu to "GoodBye".


```@BBPARSER@Greeting@mod_msu@this.logInfo("Contact the MSU team using the following email adress:\n@msu.team\@protonmail.com@");```

This will be turned into 'data/mod_msu/Greeting.nut' with the following content:
```squirrel
this.logInfo("Contact the MSU team using the following email adress:\n
msu.team@protonmail.com
");
```
