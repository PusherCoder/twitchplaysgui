# Twitch Plays GUI
Expands upon the "[Twitch Plays](https://www.dougdoug.com/twitchplays)" code by DougDoug to add a graphical user interface.

# What Does It Do?
Twitch Plays GUI allows you to connect to the chat of any stream on Twitch and execute specific mouse and/or keyboard actions based on commands typed into chat. For example, if someone types "jump" you can have that translate to pressing the Spacebar key on your keyboard. Multiple chat commands can be aliased to the same group of actions, and multiple actions can be chained together to a single command to create complex interactions.

# How Do I Install It?
As a preface to this section, the last time this was updated was in February 2023. If you're viewing this document several years later, I probably can't help you install it. Though in retrospect it's probably more worrisome that anyone would be referencing this repository after all that time.

1. Install [Python](https://www.python.org/) which must be at least Python 3.
2. Download a copy of the repository or check out a copy (if you're savy with git).
3. Run _first_time_setup.bat_ from the downloaded files. This batch command will attempt to install the virtual environment automatically. However, you can manually install it by running the following two commands:
* `python -m venv ./venv` (Note that it might be either python or py depending on your install)
* `.\venv\Scripts\python.exe -m pip install -r requirements.txt`
4. Assuming Step 3 worked, it should launch automatically. If you had to do that step manually, run _launch.bat_.

# How Do I Use It?
1. Run _launch.bat_ to launch the program any time after it is installed.
2. Type in the Twitch channel name that you want to connect to the chat of in the *Twitch Name:* box.
3. Click *Connect* and verify that the connection was successful in the accompanying command window.
4. To add a command, click the *Add Command* button.
5. Type in the text that will trigger the command into the *Chat Text* box. Multiple commands for the same action can be separated by a backslash. For example, "W/Forward/Go" could be typed in to make "W", "Forward", and "Go" all trigger the same commands.
6. Add actions and configure them accordingly. Each action should be fairly self-explanatory.
7. The program will always be listening for new commands unless you check the *Disable* box.
8. You can load or save command profiles by using the appropriate buttons.
