#####################################################################################
#
# NAME: twitchplays.py
#
# DESCRIPTION:
#   Provides a more robust GUI interface for setting up a "Twitch Chat to Keyboard
#   and Mouse" interface. In other words, it makes it easier to dynamically set up
#   that kind of interface rather than having to dick with the Python code directly.
#
# Designed by SlipstreamWorks
#
# Based on code provided by DougDoug (https://www.dougdoug.com/twitchplays)
#
# Distributed under the GNU General Public License v3.0
#
#####################################################################################

#####################################################################################
#                                 GENERAL INCLUDES                                  #
#####################################################################################

import concurrent.futures
from csv import reader, writer
import ctypes
import keyboard
import json
import pydirectinput
import pyautogui
import pynput
import random
import re
import socket
from threading import Thread
import time
from tkinter import *
from tkinter.filedialog import askopenfilename, asksaveasfilename
from tkinter.messagebox import showerror

#####################################################################################
#                                 GLOBAL CONSTANTS                                  #
#####################################################################################

#--------------------------------------------------------------------------------
# G_MESSAGE_RATE controls how fast we process incoming Twitch Chat messages. It's
# the number of seconds it will take to handle all messages in the queue.
# This is used because Twitch delivers messages in "batches", rather than one at
# a time. So we process the messages over G_MESSAGE_RATE duration, rather than
# processing the entire batch at once.
# A smaller number means we go through the message queue faster, but we will run
# out of messages faster and activity might "stagnate" while waiting for a new
# batch. 
# A higher number means we go through the queue slower, and messages are more
# evenly spread out, but delay from the viewers' perspective is higher.
# You can set this to 0 to disable the queue and handle all messages immediately.
# However, then the wait before another "batch" of messages is more noticeable.
#--------------------------------------------------------------------------------
G_MESSAGE_RATE = 0.5

#--------------------------------------------------------------------------------
# G_MAX_QUEUE_LENGTH limits the number of commands that will be processed in a
# given "batch" of messages. 
# e.g. if you get a batch of 50 messages, you can choose to only process the
# first 10 of them and ignore the others.
# This is helpful for games where too many inputs at once can actually hinder the
# gameplay.
# Setting to ~50 is good for total chaos, ~5-10 is good for 2D platformers
#--------------------------------------------------------------------------------
G_MAX_QUEUE_LENGTH = 20

#--------------------------------------------------------------------------------
# Maximum number of threads you can process at a time. Recommend making this
# smaller if your computer has a lot of things on its mind.
#--------------------------------------------------------------------------------
G_MAX_WORKERS = 100

G_MAX_TIME_TO_WAIT_FOR_LOGIN = 3

SendInput = ctypes.windll.user32.SendInput

#--------------------------------------------------------------------------------
# This table of key codes was originally derived from the DougDoug script, which
# itself pulled it from the following Microsoft documentation:
# https://docs.microsoft.com/en-us/previous-versions/visualstudio/visual-studio-6.0/aa299374(v=vs.60)
#
# The list is ordered in what I would hope is a kind of logical order, since it
# doubles as the seed for the dropdown menu on the command list.
#--------------------------------------------------------------------------------
G_KEY_DICTIONARY = {
    '':       0x00,
    
    'A':      0x1E,
    'B':      0x30,
    'C':      0x2E,
    'D':      0x20,
    'E':      0x12,
    'F':      0x21,
    'G':      0x22,
    'H':      0x23,
    'I':      0x17,
    'J':      0x24,
    'K':      0x25,
    'L':      0x26,
    'M':      0x32,
    'N':      0x31,
    'O':      0x18,
    'P':      0x19,
    'Q':      0x10,
    'R':      0x13,
    'S':      0x1F,
    'T':      0x14,
    'U':      0x16,
    'V':      0x2F,
    'W':      0x11,
    'X':      0x2D,
    'Y':      0x15,
    'Z':      0x2C,
    
    '1':      0x02,
    '2':      0x03,
    '3':      0x04,
    '4':      0x05,
    '5':      0x06,
    '6':      0x07,
    '7':      0x08,
    '8':      0x09,
    '9':      0x0A,
    '0':      0x0B,
    
    '-':      0x0C,
    '=':      0x0D,
    '[':      0x1A,
    ']':      0x1B,
    ';':      0x27,
    '~':      0x29,
    ',':      0x33,
    '.':      0x34,
    
    'F1':     0x3B,
    'F2':     0x3C,
    'F3':     0x3D,
    'F4':     0x3E,
    'F5':     0x3F,
    'F6':     0x40,
    'F7':     0x41,
    'F8':     0x42,
    'F9':     0x43,
    'F10':    0x44,
    'F11':    0x57,
    'F12':    0x58,
    
    'N1':     0x4F,
    'N2':     0x50,
    'N3':     0x51,
    'N4':     0x4B,
    'N5':     0x4C,
    'N6':     0x4D,
    'N7':     0x47,
    'N8':     0x48,
    'N9':     0x49,
    'N0':     0x52,
    'N-':     0x4A,
    'N+':     0x4E,
    'N.':     0x53,
    
    'ESC':    0x01,
    'BKSP':   0x0E,
    'TAB':    0x0F,
    'ENTER':  0x1C,
    'LCTRL':  0x1D,
    'APOS':   0x28,
    'LSHIFT': 0x2A,
    'FDSLSH': 0x2B,
    'BKSLSH': 0x35,
    'RSHIFT': 0x36,
    'PRTSCN': 0x37,
    'LALT':   0x38,
    'SPACE':  0x39,
    'CAPS':   0x3A,
    'NUMLCK': 0x45,
    'DEL':    0x53,
    'NENTER': 0x9C,
    'NBKSLH': 0xB5,
    
    'UP':     0xC8,
    'LEFT':   0xCB,
    'RIGHT':  0xCD,
    'DOWN':   0xD0
}

G_KEY_DICTIONARY_LIST = list(G_KEY_DICTIONARY.keys())

#####################################################################################
#                                 GLOBAL VARIABLES                                  #
#####################################################################################

g_commandFrame = None
g_commandList  = []
g_connected    = False
g_disabled     = None
g_streamerName = None
g_twitch       = None
g_window       = None
g_windowOpen   = True
 
#####################################################################################
#                                     CLASSES                                       #
#####################################################################################

#------------------------------------------------------------------------------------
# CLASS NAME: ComputerAction
#
# DESCRIPTION:
#   Provides the interface for a keyboard or mouse command.
#------------------------------------------------------------------------------------

class ComputerAction:

    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: __init__
    #
    # DESCRIPTION:
    #   Initialize the class variables.
    #--------------------------------------------------------------------------------
    def __init__( self, p_actionType, p_loadedData=None ):
        #----------------------------------------------------------------------------
        # Declare instance variables
        #----------------------------------------------------------------------------
        self.actionType = p_actionType
        self.delete = False
        
        self.keyButtonValue = StringVar()
        self.keyHoldButton = None
        self.keyReleaseButton = None
        self.keyTapButton = None
        self.keyTapTime = None
        self.keyTapTimeSave = '500'
        self.keyName = StringVar()
        
        self.mouseButtonValue = StringVar()
        self.mouseLeftButton = None
        self.mouseRightButton = None
        self.mouseMiddleButton = None
        self.mouseMoveButton = None
        self.mouseX = None
        self.mouseXSave = '0'
        self.mouseY = None
        self.mouseYSave = '0'
        self.mouseHoldTime = None
        self.mouseHoldTimeSave = '500'
        self.mouseRelative = IntVar()
        
        self.waitTime = None
        self.waitTimeSave = '500'
        
        #----------------------------------------------------------------------------
        # If data was passed in (if there was a load), initialize the action data
        #
        # The order in which these array items are used must be kept in perfect sync
        # with the f_saveData function down below, because if we don't load the data
        # in the same order that we saved it, we're gonna have a bad time.
        #----------------------------------------------------------------------------
        if p_loadedData != None:
            if self.actionType == 'keyboard':
                self.keyButtonValue.set( p_loadedData[0] )
                self.keyTapTimeSave = p_loadedData[1]
                self.keyName.set( p_loadedData[2] )
            elif self.actionType == 'mouse':
                self.mouseButtonValue.set( p_loadedData[0] )
                self.mouseXSave = p_loadedData[1]
                self.mouseYSave = p_loadedData[2]
                self.mouseHoldTimeSave = p_loadedData[3]
                self.mouseRelative.set( p_loadedData[4] )
            elif self.actionType == 'wait':
                self.waitTimeSave = p_loadedData[0]

    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_holdKey
    #
    # DESCRIPTION:
    #   Hold a keyboard key.
    #--------------------------------------------------------------------------------
    def f_holdKey( self, p_hexKeyCode ):
        extra = ctypes.c_ulong(0)
        ii_ = pynput._util.win32.INPUT_union()
        ii_.ki = pynput._util.win32.KEYBDINPUT( 0, p_hexKeyCode, 0x0008, 0, ctypes.cast( ctypes.pointer(extra), ctypes.c_void_p ) )
        x = pynput._util.win32.INPUT( ctypes.c_ulong(1), ii_ )
        SendInput( 1, ctypes.pointer(x), ctypes.sizeof(x) )

    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_releaseKey
    #
    # DESCRIPTION:
    #   Release a keyboard key.
    #--------------------------------------------------------------------------------
    def f_releaseKey( self, p_hexKeyCode ):
        extra = ctypes.c_ulong(0)
        ii_ = pynput._util.win32.INPUT_union()
        ii_.ki = pynput._util.win32.KEYBDINPUT( 0, p_hexKeyCode, 0x0008 | 0x0002, 0, ctypes.cast( ctypes.pointer(extra), ctypes.c_void_p ) )
        x = pynput._util.win32.INPUT(ctypes.c_ulong(1), ii_)
        SendInput( 1, ctypes.pointer(x), ctypes.sizeof(x) )

    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_tapKey
    #
    # DESCRIPTION:
    #   Taps a key by holding it down for a specific amount of time and then
    #   releasing it.
    #--------------------------------------------------------------------------------
    def f_tapKey( self, p_hexKeyCode, p_milliseconds ):
        self.f_holdKey( p_hexKeyCode )
        time.sleep( p_milliseconds / 1000 )
        self.f_releaseKey( p_hexKeyCode )
        
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_draw
    #
    # DESCRIPTION:
    #   Draw the action interface.
    #--------------------------------------------------------------------------------
    def f_draw( self, p_parentFrame ):
        #----------------------------------------------------------------------------
        # If this action frame is supposed to be deleted, return early and signal
        # that it needs to be destroyed
        #----------------------------------------------------------------------------
        if self.delete:
            return False
            
        #----------------------------------------------------------------------------
        # Create the frame for the action and pack it
        #----------------------------------------------------------------------------
        l_frame = Frame( p_parentFrame, height=10 )
        l_frame.pack( side=TOP, fill='x' )
        
        #----------------------------------------------------------------------------
        # If this is a keyboard action, generate the keyboard interface
        #----------------------------------------------------------------------------
        if self.actionType == 'keyboard':
            l_frame.config( bg='thistle2' )
            
            #------------------------------------------------------------------------
            # Create the option menu
            #------------------------------------------------------------------------
            Label( l_frame, text='Key:', bg='thistle2' ).pack( side=LEFT )         
            l_key = OptionMenu( l_frame, self.keyName, *G_KEY_DICTIONARY_LIST )
            l_key.config( width=10, bg='thistle2' )
            l_key.pack( side=LEFT )
                
            #------------------------------------------------------------------------
            # Create the radio button for the key action
            #------------------------------------------------------------------------
            self.keyHoldButton = Radiobutton( l_frame, text='Hold', variable=self.keyButtonValue, value='hold', bg='thistle2' )
            self.keyHoldButton.pack( side=LEFT ) 
            self.keyReleaseButton = Radiobutton( l_frame, text='Release', variable=self.keyButtonValue, value='release', bg='thistle2' )
            self.keyReleaseButton.pack( side=LEFT ) 
            self.keyTapButton = Radiobutton( l_frame, text='Tap', variable=self.keyButtonValue, value='tap', bg='thistle2' )
            self.keyTapButton.pack( side=LEFT ) 
            
            #------------------------------------------------------------------------
            # Initialize the radio menu with the current selection, since it resets
            # on a redraw
            #
            # Assume we want the Tap action by default if none are selected
            #------------------------------------------------------------------------ 
            if self.keyButtonValue.get() == 'hold':
                self.keyHoldButton.select()
            elif self.keyButtonValue.get() == 'release':
                self.keyReleaseButton.select()
            else:
                self.keyTapButton.select()
            
            #------------------------------------------------------------------------
            # Set up a text box for the tap duration
            #------------------------------------------------------------------------
            Label( l_frame, text='Tap duration (ms):', bg='thistle2' ).pack( side=LEFT )
            self.keyTapTime = Text( l_frame, width=5, height=1, bg='thistle2' )
            self.keyTapTime.pack( side=LEFT ) 
            self.keyTapTime.insert( END, self.keyTapTimeSave )
            
            #------------------------------------------------------------------------
            # Add a button that allows us to delete the action
            #------------------------------------------------------------------------
            Button( l_frame, text='X', height=1, command=self.f_signalDeletion, bg='red' ).pack( side=RIGHT, padx=10 )
        
        #----------------------------------------------------------------------------
        # If this is a mouse action, generate the mouse interface
        #----------------------------------------------------------------------------
        elif self.actionType == 'mouse':
            l_frame.config( bg='powderblue' )
                
            #------------------------------------------------------------------------
            # Create an upper frame and the radio buttons for the different mouse
            # actions
            #------------------------------------------------------------------------
            l_upperMouseFrame = Frame( l_frame, bg='powderblue' )
            l_upperMouseFrame.pack( side=TOP, fill=X, expand=TRUE )
            self.mouseLeftButton = Radiobutton( l_upperMouseFrame, text='Left Click', variable=self.mouseButtonValue, value='lc', bg='powderblue' )
            self.mouseLeftButton.pack( side=LEFT )
            self.mouseRightButton = Radiobutton( l_upperMouseFrame, text='Right Click', variable=self.mouseButtonValue, value='rc', bg='powderblue' )
            self.mouseRightButton.pack( side=LEFT )
            self.mouseMiddleButton = Radiobutton( l_upperMouseFrame, text='Middle Click', variable=self.mouseButtonValue, value='mc', bg='powderblue' )
            self.mouseMiddleButton.pack( side=LEFT )
            self.mouseMoveButton = Radiobutton( l_upperMouseFrame, text='Move Mouse', variable=self.mouseButtonValue, value='move', bg='powderblue' )
            self.mouseMoveButton.pack( side=LEFT )
            
            #------------------------------------------------------------------------
            # Initialize the radio menu with the current selection, since it resets
            # on a redraw
            #
            # Assume we want the Left Click action by default if none are selected
            #------------------------------------------------------------------------ 
            if self.mouseButtonValue.get() == 'rc':
                self.mouseRightButton.select()
            elif self.mouseButtonValue.get() == 'mc':
                self.mouseMiddleButton.select()
            elif self.mouseButtonValue.get() == 'move':
                self.mouseMoveButton.select()
            else:
                self.mouseLeftButton.select()
            
            #------------------------------------------------------------------------
            # Create a lower frame and fill it with the details of the mouse
            # actions
            #------------------------------------------------------------------------
            l_lowerMouseFrame = Frame( l_frame, bg='powderblue' )
            l_lowerMouseFrame.pack( side=TOP, fill=X, expand=TRUE )
            Label( l_lowerMouseFrame, text='Coordinates:', bg='powderblue' ).pack( side=LEFT )
            self.mouseX = Text( l_lowerMouseFrame, width=5, height=1, bg='powderblue' )
            self.mouseX.pack( side=LEFT )
            self.mouseX.insert( END, self.mouseXSave )
            self.mouseY = Text( l_lowerMouseFrame, width=5, height=1, bg='powderblue' )
            self.mouseY.pack( side=LEFT )
            self.mouseY.insert( END, self.mouseYSave )
            Checkbutton( l_lowerMouseFrame, text='Relative', variable=self.mouseRelative, onvalue=True, offvalue=False, bg='powderblue' ).pack( side=LEFT, padx=5 )
            Label( l_lowerMouseFrame, text='Hold Time:', bg='powderblue' ).pack( side=LEFT )
            self.mouseHoldTime = Text( l_lowerMouseFrame, width=5, height=1, bg='powderblue' )
            self.mouseHoldTime.pack( side=LEFT )
            self.mouseHoldTime.insert( END, self.mouseHoldTimeSave )
            
            #------------------------------------------------------------------------
            # Add a button that allows us to delete the action
            #------------------------------------------------------------------------
            Button( l_upperMouseFrame, text='X', height=1, command=self.f_signalDeletion, bg='red' ).pack( side=RIGHT, padx=10 )
        
        #----------------------------------------------------------------------------
        # If this is any other action, assume its a wait interface
        #----------------------------------------------------------------------------
        else:
            l_frame.config( bg='azure2' )
            #------------------------------------------------------------------------
            # Set up a text box for the wait duration
            #------------------------------------------------------------------------
            Label( l_frame, text='Wait duration (ms):', bg='azure2' ).pack( side=LEFT )
            self.waitTime = Text( l_frame, width=5, height=1, bg='azure2' )
            self.waitTime.pack( side=LEFT ) 
            self.waitTime.insert( END, self.waitTimeSave )
            
            #------------------------------------------------------------------------
            # Add a button that allows us to delete the action
            #------------------------------------------------------------------------
            Button( l_frame, text='X', height=1, command=self.f_signalDeletion, bg='red' ).pack( side=RIGHT, padx=10 )
            
        return True
        
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_process
    #
    # DESCRIPTION:
    #   Triggers a specific keyboard, mouse, or wait action depending on the type
    #   of this action field and the options selected within the type.
    #--------------------------------------------------------------------------------
    def f_process( self ):
        #----------------------------------------------------------------------------
        # Perform keyboard actions
        #----------------------------------------------------------------------------
        if self.actionType == 'keyboard':
            if self.keyButtonValue.get() == 'hold':
                self.f_holdKey( G_KEY_DICTIONARY[ self.keyName.get() ] )
            elif self.keyButtonValue.get() == 'release':
                self.f_releaseKey( G_KEY_DICTIONARY[ self.keyName.get() ] )
            elif self.keyButtonValue.get() == 'tap':
                self.f_tapKey( G_KEY_DICTIONARY[ self.keyName.get() ], int(self.keyTapTime.get( '1.0', 'end-1c' )) )
        
        #----------------------------------------------------------------------------
        # Perform mouse actions
        #----------------------------------------------------------------------------
        elif self.actionType == 'mouse':
            if self.mouseButtonValue.get() == 'lc':
                pydirectinput.leftClick( x=(int(self.mouseX.get( '1.0', 'end-1c' )) if self.mouseX.get( '1.0', 'end-1c' ) != '' else None), y=(int(self.mouseY.get( '1.0', 'end-1c' )) if self.mouseY.get( '1.0', 'end-1c' ) != '' else None) )
            elif self.mouseButtonValue.get() == 'rc':
                pydirectinput.rightClick( x=(int(self.mouseX.get( '1.0', 'end-1c' )) if self.mouseX.get( '1.0', 'end-1c' ) != '' else None), y=(int(self.mouseY.get( '1.0', 'end-1c' )) if self.mouseY.get( '1.0', 'end-1c' ) != '' else None) )
            elif self.mouseButtonValue.get() == 'mc':
                pydirectinput.middleClick( x=(int(self.mouseX.get( '1.0', 'end-1c' )) if self.mouseX.get( '1.0', 'end-1c' ) != '' else None), y=(int(self.mouseY.get( '1.0', 'end-1c' )) if self.mouseY.get( '1.0', 'end-1c' ) != '' else None) )
            elif self.mouseButtonValue.get() == 'move':
                pydirectinput.moveRel( xOffset=(int(self.mouseX.get( '1.0', 'end-1c' )) if self.mouseX.get( '1.0', 'end-1c' ) != '' else 0), yOffset=(int(self.mouseY.get( '1.0', 'end-1c' )) if self.mouseY.get( '1.0', 'end-1c' ) != '' else 0), relative=self.mouseRelative.get() )
        
        #----------------------------------------------------------------------------
        # Perform wait actions
        #----------------------------------------------------------------------------
        elif self.actionType == 'wait':
            time.sleep( int(self.waitTime.get) / 1000 )
        
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_save
    #
    # DESCRIPTION:
    #   Saves off the state of the action because we're about to destroy and recreate
    #   the action.
    #--------------------------------------------------------------------------------
    def f_save( self ):
        #----------------------------------------------------------------------------
        # Save off the key tap duration
        #----------------------------------------------------------------------------
        if self.keyTapTime != None:
            self.keyTapTimeSave = self.keyTapTime.get( '1.0', 'end-1c' )
            
        #----------------------------------------------------------------------------
        # Save off the wait duration
        #----------------------------------------------------------------------------
        if self.waitTime != None:
            self.waitTimeSave = self.waitTime.get( '1.0', 'end-1c' )
            
        #----------------------------------------------------------------------------
        # Save off the mouse X, Y, and hold duration
        #----------------------------------------------------------------------------
        if self.mouseX != None:
            self.mouseXSave = self.mouseX.get( '1.0', 'end-1c' )
        if self.mouseY != None:
            self.mouseYSave = self.mouseY.get( '1.0', 'end-1c' )
        if self.mouseHoldTime != None:
            self.mouseHoldTimeSave = self.mouseHoldTime.get( '1.0', 'end-1c' )
        
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_saveData
    #
    # DESCRIPTION:
    #   Generates an array of saved data that will be used to populate the save file.
    #--------------------------------------------------------------------------------
    def f_saveData( self ):
        l_returnData = [ self.actionType ]
        
        #----------------------------------------------------------------------------
        # Load the rest of the data, as defined by the action type, into the array
        # and pass it back
        #
        # Note that this save order must stay aligned with the load order in the
        # __init__ function, because once again we'll have a bad time if we screw
        # up the ordering of the saved and loaded data.
        #----------------------------------------------------------------------------
        if self.actionType == 'keyboard':
            l_returnData.append( self.keyButtonValue.get() )
            l_returnData.append( self.keyTapTimeSave )
            l_returnData.append( self.keyName.get() )
        elif self.actionType == 'mouse':
            l_returnData.append( self.mouseButtonValue.get() )
            l_returnData.append( self.mouseXSave )
            l_returnData.append( self.mouseYSave )
            l_returnData.append( self.mouseHoldTimeSave )
            l_returnData.append( self.mouseRelative.get() )
        elif self.actionType == 'wait':
            l_returnData.append( self.waitTimeSave )
            
        return l_returnData
        
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_signalDeletion
    #
    # DESCRIPTION:
    #   Saves off the state of the action because we're about to destroy and recreate
    #   the action.
    #--------------------------------------------------------------------------------
    def f_signalDeletion( self ):
        self.delete = True
        f_redraw()


#------------------------------------------------------------------------------------
# CLASS NAME: TwitchCommand
#
# DESCRIPTION:
#   Provides the interface for an individual command, which links a specific chat
#   input from Twitch to a specific function on the PC running the script.
#------------------------------------------------------------------------------------

class TwitchCommand:
    
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: __init__
    #
    # DESCRIPTION:
    #   Initialize the class variables.
    #--------------------------------------------------------------------------------
    def __init__( self, p_commandText=None, p_actionData=None ):
        #----------------------------------------------------------------------------
        # Declare instance variables
        #----------------------------------------------------------------------------
        self.actionList = []
        self.chatText = None
        self.delete = False
        
        #----------------------------------------------------------------------------
        # Load the command text if some was passed in (if the script was loaded),
        # otherwise just initialize it to a blank string
        #----------------------------------------------------------------------------
        if p_commandText == None:
            self.savedText = ''
        else:
            self.savedText = p_commandText
        
        #----------------------------------------------------------------------------
        # If there is action data (if the script was loaded), initialize the action
        # list
        #----------------------------------------------------------------------------
        if p_actionData != None:
            for i_action in p_actionData:
                print( 'Adding Action {0} with data {1}'.format( i_action[0], i_action[1:] ) )
                self.actionList.append( ComputerAction( i_action[0], i_action[1:] ) )
    
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_handleAddKeyboard
    #
    # DESCRIPTION:
    #   Add a Keyboard action to the action list.
    #--------------------------------------------------------------------------------
    def f_handleAddKeyboard( self ):
        self.actionList.append( ComputerAction( 'keyboard' ) )
        f_redraw()
    
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_handleAddMouse
    #
    # DESCRIPTION:
    #   Add a Mouse action to the action list.
    #--------------------------------------------------------------------------------
    def f_handleAddMouse( self ):
        self.actionList.append( ComputerAction( 'mouse' ) )
        f_redraw()
    
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_handleAddWait
    #
    # DESCRIPTION:
    #   Add a Wait action to the action list.
    #--------------------------------------------------------------------------------
    def f_handleAddWait( self ):
        self.actionList.append( ComputerAction( 'wait' ) )
        f_redraw()
    
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_check
    #
    # DESCRIPTION:
    #   Check to see if the passed-in Twitch chat message is supposed to be processed
    #   by this command.
    #--------------------------------------------------------------------------------
    def f_check( self, p_message ):
        #----------------------------------------------------------------------------
        # Check chat message against command text
        #----------------------------------------------------------------------------
        l_command = self.chatText.get( '1.0', 'end-1c' )
        
        #----------------------------------------------------------------------------
        # If there is a match, perform the list of actions assigned to this command
        #----------------------------------------------------------------------------
        if l_command == p_message:
            print( 'Command Correctly Received' )
            for i_action in self.actionList:
                i_action.f_process()
    
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_draw
    #
    # DESCRIPTION:
    #   Draw the command interface.
    #--------------------------------------------------------------------------------
    def f_draw( self, p_parentFrame ):
        #----------------------------------------------------------------------------
        # If this command frame is supposed to be deleted, return early and signal
        # that it needs to be destroyed
        #----------------------------------------------------------------------------
        if self.delete:
            return False
            
        #----------------------------------------------------------------------------
        # Create the frame for the command interface and pack it
        #----------------------------------------------------------------------------
        l_frame = Frame( p_parentFrame, height=10 )
        l_frame.pack( side=TOP, fill='x' )
        
        #----------------------------------------------------------------------------
        # Add a label and text box for the command text
        #----------------------------------------------------------------------------
        Label( l_frame, text='Chat Text:' ).pack( side=LEFT )
        self.chatText = Text( l_frame, width=10, height=1 )
        self.chatText.pack( side=LEFT )
        self.chatText.insert( END, self.savedText )
        
        #----------------------------------------------------------------------------
        # Add buttons to add actions to the action list for this command
        #----------------------------------------------------------------------------
        Button( l_frame, text='Add Keyboard Action', width=17, height=1, command=self.f_handleAddKeyboard ).pack( side=LEFT )
        Button( l_frame, text='Add Mouse Action', width=17, height=1, command=self.f_handleAddMouse ).pack( side=LEFT )
        Button( l_frame, text='Add Wait', width=17, height=1, command=self.f_handleAddWait ).pack( side=LEFT )
        
        #----------------------------------------------------------------------------
        # Draw the action list
        #----------------------------------------------------------------------------
        self.actionList = [ i_action for i_action in self.actionList if i_action.f_draw( p_parentFrame ) ]     
            
        #----------------------------------------------------------------------------
        # Add a button that allows us to delete the action
        #----------------------------------------------------------------------------
        Button( l_frame, text='X', height=1, command=self.f_signalDeletion, bg='red' ).pack( side=RIGHT, padx=10 )

        return True
        
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_save
    #
    # DESCRIPTION:
    #   Saves off the state of the command fields because we're about to destroy
    #   and recreate the command.
    #--------------------------------------------------------------------------------
    def f_save( self ):
        #----------------------------------------------------------------------------
        # Save off the chat text
        #----------------------------------------------------------------------------
        if self.chatText != None:
            self.savedText = self.chatText.get( '1.0', 'end-1c' )
            
        #----------------------------------------------------------------------------
        # Loop through the list of actions and save off any necessary data
        #----------------------------------------------------------------------------
        for i_action in self.actionList:
            i_action.f_save()
        
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_saveData
    #
    # DESCRIPTION:
    #   Generates an array of saved data that will be used to populate the save file.
    #--------------------------------------------------------------------------------
    def f_saveData( self ):
        l_returnData = [ [ self.savedText, len(self.actionList) ] ]
        for i_action in self.actionList:
            l_returnData.append( i_action.f_saveData() )
        
        return l_returnData
        
    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_signalDeletion
    #
    # DESCRIPTION:
    #   Saves off the state of the action because we're about to destroy and recreate
    #   the action.
    #--------------------------------------------------------------------------------
    def f_signalDeletion( self ):
        self.delete = True
        f_redraw()

#------------------------------------------------------------------------------------
# CLASS NAME: Twitch
#
# DESCRIPTION:
#   Provides the interface to connect with the Twitch chat of the specified channel.
#------------------------------------------------------------------------------------

class Twitch:
    #--------------------------------------------------------------------------------
    # Class variables
    #--------------------------------------------------------------------------------
    re_prog = None
    sock = None
    partial = b''
    login_ok = False
    channel = ''
    login_timestamp = 0

    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_connect
    #
    # DESCRIPTION:
    #   Sets up the initial Twitch chat connection.
    #--------------------------------------------------------------------------------
    def f_connect( self, p_channel ):
        if self.sock: self.sock.close()
        self.sock = None
        self.partial = b''
        self.login_ok = False
        self.channel = p_channel.lower()

        #----------------------------------------------------------------------------
        # Compile the regular expression that will be used to read chat messages
        #----------------------------------------------------------------------------
        self.re_prog = re.compile( b'^(?::(?:([^ !\r\n]+)![^ \r\n]*|[^ \r\n]*) )?([^ \r\n]+)(?: ([^:\r\n]*))?(?: :([^\r\n]*))?\r\n', re.MULTILINE )

        #----------------------------------------------------------------------------
        # Create the socket connection and attempt the connection
        #----------------------------------------------------------------------------
        print( 'Connecting to Twitch...' )
        self.sock = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
        self.sock.connect( ('irc.chat.twitch.tv', 6667) )

        #----------------------------------------------------------------------------
        # Log into Twitch as an anonymous user
        #
        # These login credentials appear to have been provided as part of the
        # original DougDoug script. I wouldn't be surprised if these credentials went
        # AWOL at some point and need to be replaced with new user-generated
        # credentials.
        #----------------------------------------------------------------------------
        l_user = 'justinfan%i' % random.randint(10000, 99999)
        print( 'Connected to Twitch. Logging in anonymously...' )
        self.sock.send( ('PASS asdf\r\nNICK %s\r\n' % l_user).encode() )

        #----------------------------------------------------------------------------
        # Set a 1-second socket timeout and log the connection time
        #----------------------------------------------------------------------------
        self.sock.settimeout( 1.0/60.0 )
        self.login_timestamp = time.time()


    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_reconnect
    #
    # DESCRIPTION:
    #   Trigger the connection sequence again.
    #--------------------------------------------------------------------------------
    def f_reconnect( self, p_delay ):
        time.sleep( p_delay )
        self.f_connect( self.channel )


    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_receive_and_parse_data
    #
    # DESCRIPTION:
    #   Receive data from Twitch chat and parse it for the text content. Return that
    #   text information as an array
    #--------------------------------------------------------------------------------
    def f_receiveAndParseData( self ):
        #----------------------------------------------------------------------------
        # Clear the buffer
        #----------------------------------------------------------------------------
        l_buffer = b''
        
        #----------------------------------------------------------------------------
        # Loop continuously until either the socket times out (meaning we've
        # collected all presently-available chat messages), there is an unexpected
        # exception, or Twitch closes our connection
        #
        # In any of the error cases, attempt to reconnect to Twitch.
        #----------------------------------------------------------------------------
        while True:
            l_received = b''
            try:
                l_received = self.sock.recv( 4096 )
            except socket.timeout:
                break
            except Exception as e:
                print( 'Unexpected connection error. Reconnecting in a second...', e )
                self.f_reconnect( 1 )
                return []
            if not l_received:
                print( 'Connection closed by Twitch. Reconnecting in 5 seconds...' )
                self.f_reconnect( 5 )
                return []
            l_buffer += l_received

        #----------------------------------------------------------------------------
        # If data was received, process it
        #----------------------------------------------------------------------------
        if l_buffer:
            #------------------------------------------------------------------------
            # If the final packet of a previous transaction was a partial packet,
            # concatinate it with the first packet of the new transmission
            #------------------------------------------------------------------------
            if self.partial:
                l_buffer = self.partial + l_buffer
                self.partial = []

            #------------------------------------------------------------------------
            # Use the RegEx to parse the raw buffer data and extract the components
            # of the chat message that we care about, including the Username, the
            # Command, Parameters, and any Trailing data
            #------------------------------------------------------------------------
            l_res = []
            l_matches = list(self.re_prog.finditer( l_buffer ))
            for i_match in l_matches:
                l_res.append({
                    'name':     ( i_match.group(1) or b'' ).decode( errors='replace' ),
                    'command':  ( i_match.group(2) or b'' ).decode( errors='replace' ),
                    'params':   list(map(lambda p: p.decode( errors='replace' ), ( i_match.group(3) or b'' ).split( b' ' ))),
                    'trailing': ( i_match.group(4) or b'' ).decode( errors='replace' ),
                })

            #------------------------------------------------------------------------
            # If there is leftover data that appears to be from a partially-received
            # message, save it off to hopefully finish with data from the next cycle
            #------------------------------------------------------------------------
            if not l_matches:
                self.partial += l_buffer
                
            #------------------------------------------------------------------------
            # Otherwise, confirm that we reached a true end to the last packet to
            # verify that we didn't just parse corrupted data
            #------------------------------------------------------------------------
            else:
                end = l_matches[-1].end()
                if end < len(l_buffer):
                    self.partial = l_buffer[end:]

                if l_matches[0].start() != 0:
                    #----------------------------------------------------------------
                    # Original print statement left for lulz and clarity
                    #----------------------------------------------------------------
                    print( 'either ddarknut fucked up or twitch is bonkers, or both I mean who really knows anything at this point' )

            #------------------------------------------------------------------------
            # Since data was likely found, return the data
            #------------------------------------------------------------------------
            return l_res

        #----------------------------------------------------------------------------
        # Since there was no data to process, return an empty array
        #----------------------------------------------------------------------------
        return []


    #--------------------------------------------------------------------------------
    # CLASS PROCEDURE NAME: f_twitch_receive_messages
    #
    # DESCRIPTION:
    #   Receive protocol messages from Twitch and parse for content
    #--------------------------------------------------------------------------------
    def f_twitchReceiveMessages( self ):
        l_privmsgs = []
        
        #----------------------------------------------------------------------------
        # Retrieve messages from Twitch, parse them using our local RegEx, and loop
        # through the resulting array
        #----------------------------------------------------------------------------
        for i_irc_message in self.f_receiveAndParseData():
            l_cmd = i_irc_message['command']
            
            #------------------------------------------------------------------------
            # For Private Messages, which are the chat messages we're after, save
            # off the Username and Message Content and put it in the array being
            # returned to the calling function
            #------------------------------------------------------------------------
            if l_cmd == 'PRIVMSG':
                l_privmsgs.append({
                    'username': i_irc_message['name'],
                    'message': i_irc_message['trailing'],
                })
                
            #------------------------------------------------------------------------
            # For Pings from Twitch, Pong right back
            #------------------------------------------------------------------------
            elif l_cmd == 'PING':
                self.sock.send(b'PONG :tmi.twitch.tv\r\n')
                
            #------------------------------------------------------------------------
            # For a successful login attempt, send the command to join the channel's
            # chat
            #------------------------------------------------------------------------
            elif l_cmd == '001':
                print( 'Successfully logged in. Joining channel %s.' % self.channel )
                self.sock.send( ( 'JOIN #%s\r\n' % self.channel ).encode() )
                self.login_ok = True
                
            #------------------------------------------------------------------------
            # For a successful join attempt, report that it was successful
            #------------------------------------------------------------------------
            elif l_cmd == 'JOIN':
                print( 'Successfully joined channel %s' % i_irc_message['params'][0] )
                
            #------------------------------------------------------------------------
            # For a Service Notice, print the notice
            #------------------------------------------------------------------------
            elif l_cmd == 'NOTICE':
                print( 'Server notice:', i_irc_message['params'], i_irc_message['trailing'] )
                
            #------------------------------------------------------------------------
            # For all other server commands, just let us know that we've received
            # them and hope nothing has gone sideways
            #------------------------------------------------------------------------
            elif l_cmd == '002': continue
            elif l_cmd == '003': continue
            elif l_cmd == '004': continue
            elif l_cmd == '375': continue
            elif l_cmd == '372': continue
            elif l_cmd == '376': continue
            elif l_cmd == '353': continue
            elif l_cmd == '366': continue
            else:
                print( 'Unhandled irc message:', i_irc_message )

        #----------------------------------------------------------------------------
        # If we have not yet successfully logged in, check to see that we haven't
        # gone beyond our timeout
        #----------------------------------------------------------------------------
        if not self.login_ok:
            if time.time() - self.login_timestamp > G_MAX_TIME_TO_WAIT_FOR_LOGIN:
                #--------------------------------------------------------------------
                # The timeout has expired, so try to reconnect to Twitch
                #--------------------------------------------------------------------
                print( 'No response from Twitch. Reconnecting...' )
                self.f_reconnect( 0 )
                return []

        return l_privmsgs

#####################################################################################
#                                DEFINED PROCEDURES                                 #
#####################################################################################

#------------------------------------------------------------------------------------
# PROCEDURE NAME: f_handleAddCommand
#
# DESCRIPTION:
#   Handles the "Add Command" button that appends a new command to the list.
#------------------------------------------------------------------------------------
def f_handleAddCommand():
    #--------------------------------------------------------------------------------
    # Import globals
    #--------------------------------------------------------------------------------
    global g_commandList
    
    #--------------------------------------------------------------------------------
    # Append a new command to the command list and redraw the command list
    #--------------------------------------------------------------------------------
    g_commandList.append(TwitchCommand())
    f_redraw()

#------------------------------------------------------------------------------------
# PROCEDURE NAME: f_handleConnect
#
# DESCRIPTION:
#   Handles the "Connect" button. Assumes that the username field is filled out, but
#   it'll throw an exception if the field is empty.
#------------------------------------------------------------------------------------
def f_handleConnect():
    #--------------------------------------------------------------------------------
    # Import globals
    #--------------------------------------------------------------------------------
    global g_connected
    global g_twitch
    
    #--------------------------------------------------------------------------------
    # Retrieve the streamer name
    #--------------------------------------------------------------------------------
    l_streamerName = g_streamerName.get( '1.0', 'end-1c' )
    
    #--------------------------------------------------------------------------------
    # If the streamer name string isn't empty, attempt to connect to Twitch and start
    # retrieving messages from that channel's chat
    #--------------------------------------------------------------------------------
    if l_streamerName != '':
        g_twitch.f_connect( l_streamerName )
        g_connected = True
        
#------------------------------------------------------------------------------------
# PROCEDURE NAME: f_handleLoad
#
# DESCRIPTION:
#   Handles loading from a CSV file. It's branded as a TTK file here for fun.
#------------------------------------------------------------------------------------
def f_handleLoad():
    #--------------------------------------------------------------------------------
    # Import globals
    #--------------------------------------------------------------------------------
    global g_commandList
    
    #--------------------------------------------------------------------------------
    # Import globals
    #--------------------------------------------------------------------------------
    print( 'Choose data file to load.' )
    l_filePath = askopenfilename( filetypes=(('TTK Files','*.ttk'), ('All Files','*.*')) )
    
    #--------------------------------------------------------------------------------
    # Check that this is a likely good file by making sure that it has the ttk file
    # extension
    #--------------------------------------------------------------------------------
    if l_filePath.lower().endswith( '.ttk' ):
        #----------------------------------------------------------------------------
        # Open the file and load the data to the command/action frames
        #----------------------------------------------------------------------------
        with open( l_filePath, newline='' ) as l_fileData:
            #------------------------------------------------------------------------
            # Parse the TTK file (really a CSV file) and create a 2D array of the
            # data contained therein
            #------------------------------------------------------------------------
            l_dataTable = list( reader( l_fileData, delimiter=',', quotechar='|' ) )
            
            #------------------------------------------------------------------------
            # Nuke the command list to delete any existing entries
            #------------------------------------------------------------------------
            g_commandList = []
            
            #------------------------------------------------------------------------
            # Cycle through each line in the file, looking for the "command" keyword
            # to let us know that we're looking at the start of a new command entry
            #------------------------------------------------------------------------
            for i_index, i_dataLine in enumerate(l_dataTable):
                if i_dataLine[0] == 'command':
                    #----------------------------------------------------------------
                    # The line will tell us the chat keyword and how many additional
                    # lines contain action data related to this command, so pass
                    # those additional lines down into the constructor
                    #----------------------------------------------------------------
                    g_commandList.append( TwitchCommand( i_dataLine[1], l_dataTable[(i_index + 1):(i_index + int(i_dataLine[2]) + 1)] ) )
                    
    #--------------------------------------------------------------------------------
    # Throw an error if the file is not a TTK file
    #--------------------------------------------------------------------------------
    else:
        showerror( 'Invalid File', 'Only TTK files may be selected.' )
    
    #--------------------------------------------------------------------------------
    # Redraw the frame to load in the new data
    #--------------------------------------------------------------------------------
    f_redraw()
        
#------------------------------------------------------------------------------------
# PROCEDURE NAME: f_handleMessage
#
# DESCRIPTION:
#   Handles each message read in from Twitch chat. The message is assumed to already
#   have been parsed for content, and the input is actually a dictionary consisting
#   of the username and the raw message text.
#------------------------------------------------------------------------------------
def f_handleMessage( p_message ):
    #--------------------------------------------------------------------------------
    # Import globals
    #--------------------------------------------------------------------------------
    global g_commandList
    
    #--------------------------------------------------------------------------------
    # Cycle through the list of commands in the command list and pass the message to
    # each of them to see if they're supposed to handle it
    #--------------------------------------------------------------------------------
    try:
        print("Got this message from " + p_message['username'].lower() + ": " + p_message['message'].lower())
        for i_command in g_commandList:
            i_command.f_check( p_message['message'].lower() )
            
    #--------------------------------------------------------------------------------
    # Stuff likes to break here because this is by far the most buggy area of the
    # program, so capture all exceptions and avoid breaking the program here
    #--------------------------------------------------------------------------------
    except Exception as e:
        print("Encountered exception: " + str(e))
        
#------------------------------------------------------------------------------------
# PROCEDURE NAME: f_handleSave
#
# DESCRIPTION:
#   Handles saving to a CSV file. It's branded as a TTK file here for fun.
#------------------------------------------------------------------------------------
def f_handleSave():
    #--------------------------------------------------------------------------------
    # In kind of a clever solution, trigger a redraw to force all the fields to be
    # updated so we can save them off
    #--------------------------------------------------------------------------------
    f_redraw()
    
    #--------------------------------------------------------------------------------
    # Prompt the user to choose a save location
    #
    # Turns out detecting what happens when the user hits "cancel" is pretty damn
    # hard with this library, so it'll just continue on and save a file that it named
    # ".ttk" to the location. Can't figure out how to fix this now.
    #--------------------------------------------------------------------------------
    print( 'Choose a location and name for the saved file.' )
    l_filePath = asksaveasfilename( filetypes=(('TTK Files','*.ttk'), ('All Files','*.*')) )
    
    #--------------------------------------------------------------------------------
    # Append ".ttk" to the filename to make sure the load check works, especially if
    # this user has chosen to hide their file extensions
    #--------------------------------------------------------------------------------
    if not l_filePath.lower().endswith( '.ttk' ):
        l_filePath = l_filePath + '.ttk'
        
    #--------------------------------------------------------------------------------
    # Open the file and instantiate a CSV writer
    #--------------------------------------------------------------------------------
    with open( l_filePath, 'w', newline='' ) as l_fileData:
        l_writer = writer( l_fileData )
        
        #----------------------------------------------------------------------------
        # Loop through the list of commands and have each of them save off their
        # data, which returns a multidimensional array starting with the command
        # parameters and ending with separate lines for each action
        #----------------------------------------------------------------------------
        for i_command in g_commandList:
            l_commandData = i_command.f_saveData()
            
            #------------------------------------------------------------------------
            # Build the "header" line and write it out
            #------------------------------------------------------------------------
            l_writer.writerow( [ 'command', l_commandData[0][0], l_commandData[0][1] ] )
            
            #------------------------------------------------------------------------
            # Cycle through all the action lines and write them out
            #------------------------------------------------------------------------
            for i_actionData in l_commandData[1:]:
                l_writer.writerow( i_actionData )
        
#------------------------------------------------------------------------------------
# PROCEDURE NAME: f_mainLoop
#
# DESCRIPTION:
#   Main loop that handles listening for new messages and doing any other
#   house-keeping that isn't already handled by the tkinter main loop. This function
#   is started in a second thread, because the tkinter main loop monopolizes the
#   original thread and leaves no room for us to do anything.
#------------------------------------------------------------------------------------
def f_mainLoop():
    #--------------------------------------------------------------------------------
    # Import globals
    #--------------------------------------------------------------------------------
    global g_connected
    global g_disabled
    global g_twitch
    global g_windowOpen

    #--------------------------------------------------------------------------------
    # Set up a blank task and message array, which are needed in later processing,
    # and build a thread pool
    #--------------------------------------------------------------------------------
    l_activeTasks = []
    l_messageQueue = []
    thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=G_MAX_WORKERS)

    #--------------------------------------------------------------------------------
    # Loop forever
    #--------------------------------------------------------------------------------
    while True:
        #----------------------------------------------------------------------------
        # If the window is closed, terminate this secondary thread to end the program
        #----------------------------------------------------------------------------
        if g_windowOpen == False:
            exit()
        
        #----------------------------------------------------------------------------
        # Sleep for 100ms here to avoid driving up the CPU usage and lagging the
        # tkinter window
        #----------------------------------------------------------------------------
        time.sleep(0.1)
        
        #----------------------------------------------------------------------------
        # Don't do any processing unless the Twitch chat connection has been
        # established
        #
        # As far as I can tell, there isn't really a way to prove that Twitch is
        # still connected, so all we can say for sure is that we attempted to
        # establish a connection and hope for the best.
        #----------------------------------------------------------------------------
        if g_connected and not g_disabled.get():
            #------------------------------------------------------------------------
            # This weird-ass statement is basically a list comprehension that takes
            # the list of tasks that are still processing and prunes out any that
            # are complete (just go with it)
            #------------------------------------------------------------------------
            l_activeTasks = [i_task for i_task in l_activeTasks if not i_task.done()]

            #------------------------------------------------------------------------
            # Pull new messages from Twitch
            #------------------------------------------------------------------------
            l_newMessages = g_twitch.f_twitchReceiveMessages()
            
            #------------------------------------------------------------------------
            # If there are new messages, add them to the queue and truncate the
            # queue to the maximum length as defined in the global constants
            #------------------------------------------------------------------------
            if l_newMessages:
                l_messageQueue += l_newMessages; # New messages are added to the back of the queue
                l_messageQueue = l_messageQueue[-G_MAX_QUEUE_LENGTH:] # Shorten the queue to only the most recent X messages

            #------------------------------------------------------------------------
            # If there are no messages to handle, update the time tracking to avoid
            # handling way too many messages the next time we receive some data
            #------------------------------------------------------------------------
            l_messagesToHandle = []
            if not l_messageQueue:
                last_time = time.time()
                
            #------------------------------------------------------------------------
            # If there are messages, calculate how many messages should be handled
            # based on the global constants
            #------------------------------------------------------------------------
            else:
                r = 1 if G_MESSAGE_RATE == 0 else (time.time() - last_time) / G_MESSAGE_RATE
                n = int(r * len(l_messageQueue))
                
                #--------------------------------------------------------------------
                # If messages need to be handled, pop them off the message queue and
                # put them into the handle list
                #--------------------------------------------------------------------
                if n > 0:
                    l_messagesToHandle = l_messageQueue[0:n]
                    del l_messageQueue[0:n]
                    last_time = time.time();

            #------------------------------------------------------------------------
            # As a safety precaution, immediately terminate the listening loop if
            # the user presses Shift and Backspace
            #------------------------------------------------------------------------
            if keyboard.is_pressed('shift+backspace'):
                exit()

            #------------------------------------------------------------------------
            # If we're handling some messages at this time, attempt to spawn off a
            # thread to handle them if there is a thread available
            #------------------------------------------------------------------------
            if not l_messagesToHandle:
                continue
            else:
                for message in l_messagesToHandle:
                    #----------------------------------------------------------------
                    # Only add a new task if we are not going to exceed the maximum
                    # amount of allowable threads
                    #----------------------------------------------------------------
                    if len(l_activeTasks) <= G_MAX_WORKERS:
                        l_activeTasks.append(thread_pool.submit(f_handleMessage, message))
                    else:
                        print(f'WARNING: active tasks ({len(l_activeTasks)}) exceeds number of workers ({G_MAX_WORKERS}). ({len(l_messageQueue)} messages in the queue)')
        
#------------------------------------------------------------------------------------
# PROCEDURE NAME: f_redraw
#
# DESCRIPTION:
#   Regenerate the command list. This function is called any time a command is being
#   added or removed from the list, because tkinter doesn't have a way to natively
#   refresh this kind of thing to my knowledge.
#------------------------------------------------------------------------------------
def f_redraw():
    #--------------------------------------------------------------------------------
    # Import globals
    #--------------------------------------------------------------------------------
    global g_commandFrame
    global g_commandList
    
    #--------------------------------------------------------------------------------
    # Cycle through the list of commands and have them save off their state, because
    # that state is going to be deleted when the frame and its children are destroyed
    #--------------------------------------------------------------------------------
    for i_command in g_commandList:
        i_command.f_save()

    #--------------------------------------------------------------------------------
    # If we currently have a command list drawn to the screen, delete the overall
    # containing frame, which SHOULD delete it and all the other tkinter junk nested
    # underneath it
    #
    # Side note: If you add a ton of commands and there seems to be a memory leak,
    # this assumption is probably incorrect and it just removes the reference to
    # the ton of tkinter junk rather than deallocating it.
    #--------------------------------------------------------------------------------
    if g_commandFrame != None:
        g_commandFrame.destroy()
        
    #--------------------------------------------------------------------------------
    # Define a function here for handling the scrollbar
    #
    # Real talk, but it took me, like, 4 days to figure out how scrollbars in
    # Tkinter work. They suck. I could clean up where this function goes, but it
    # works now and I don't want to break it.
    #--------------------------------------------------------------------------------
    def onFrameConfigure(canvas):
        l_canvas.configure(scrollregion=l_canvas.bbox("all"))
        
    #--------------------------------------------------------------------------------
    # Create a new frame to hold the command list
    #--------------------------------------------------------------------------------
    g_commandFrame = Frame( g_window )
    g_commandFrame.pack( fill=BOTH, expand=TRUE )
    
    #--------------------------------------------------------------------------------
    # Create a canvas, inner frame, and scrollbar
    #--------------------------------------------------------------------------------
    l_canvas = Canvas( g_commandFrame, bd=0, highlightthickness=0 )
    l_innerFrame = Frame( l_canvas )
    l_vscrollbar = Scrollbar( g_commandFrame, orient=VERTICAL, command=l_canvas.yview )
    l_canvas.configure( yscrollcommand=l_vscrollbar.set )
    
    #--------------------------------------------------------------------------------
    # Pack those components and set up the callback so the scrollbar starts working
    #--------------------------------------------------------------------------------
    l_vscrollbar.pack( fill=Y, side=RIGHT )
    l_canvas.pack( side=LEFT, fill=BOTH, expand=TRUE )
    l_canvas.create_window( 0, 0, window=l_innerFrame, anchor=NW )
    l_innerFrame.bind( '<Configure>', lambda event, canvas=l_canvas: onFrameConfigure( canvas ) )
    
    #--------------------------------------------------------------------------------
    # Cycle through the list of commands again and redraw them to the application
    #--------------------------------------------------------------------------------
    g_commandList = [ i_command for i_command in g_commandList if i_command.f_draw( l_innerFrame ) ]  
        
    #--------------------------------------------------------------------------------
    # Add a button at the bottom of the list to add more commands
    #--------------------------------------------------------------------------------
    Button( l_innerFrame, text='Add Command', command=f_handleAddCommand ).pack( side=TOP, fill='x' )
    

#####################################################################################
#                                   MAIN SCRIPT                                     #
#####################################################################################

#------------------------------------------------------------------------------------
# Instantiate the Twitch application
#------------------------------------------------------------------------------------
g_twitch = Twitch()

#------------------------------------------------------------------------------------
# Create the main tkinter window
#------------------------------------------------------------------------------------
g_window = Tk()
g_window.title( 'Twitch to Keyboard' )
g_window.geometry( '600x800' )

#------------------------------------------------------------------------------------
# Create the main control bar frame and pack it at the top
#------------------------------------------------------------------------------------
l_mainControlFrame = Frame( g_window )
l_mainControlFrame.pack( side=TOP, fill='x' )

#------------------------------------------------------------------------------------
# Set up the controls in the main control bar
#------------------------------------------------------------------------------------
Label( l_mainControlFrame, text='Twitch Name:' ).pack( side=LEFT, padx=5 )
g_streamerName = Text( l_mainControlFrame, width=20, height=1 )
g_streamerName.pack( side=LEFT, padx=5 )
Button( l_mainControlFrame, text='Connect', width=10, height=1, command=f_handleConnect ).pack( side=LEFT, padx=5 )
g_disabled = IntVar()
Checkbutton( l_mainControlFrame, text='Disable', variable=g_disabled, onvalue=True, offvalue=False ).pack( side=LEFT, padx=5 )
Button( l_mainControlFrame, text='Load', width=6, height=1, command=f_handleLoad ).pack( side=LEFT, padx=5 )
Button( l_mainControlFrame, text='Save', width=6, height=1, command=f_handleSave ).pack( side=LEFT, padx=5 )

#------------------------------------------------------------------------------------
# Trigger a redraw to set up the command list
#------------------------------------------------------------------------------------
f_redraw()

#------------------------------------------------------------------------------------
# Kick off a second thread to handle the Twitch message processing
#------------------------------------------------------------------------------------
Thread( target=f_mainLoop ).start()

#------------------------------------------------------------------------------------
# Start up the tkinter main loop to handle window drawing
#------------------------------------------------------------------------------------
g_window.mainloop()

#------------------------------------------------------------------------------------
# If we get here, the window has been closed, so update the variable to let the
# second thread know it can die
#------------------------------------------------------------------------------------
g_windowOpen = False
