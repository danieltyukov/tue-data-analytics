"""Python module to record mouse trajectories.

Created for Data Analytics for Engineers, TU/e.

Authors: Mike Holenderski and Jim Portegies."""

import math
import os
import sys
import platform
import random
import time

import tkinter as tk
from tkinter import messagebox

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

if os.name == 'nt' and platform.release() == '10':
    import ctypes
    from ctypes import windll
    from winreg import ConnectRegistry, HKEY_CURRENT_USER, EnumValue,\
                       OpenKey, QueryValueEx, CloseKey, QueryInfoKey

class MouseExperiment:
    """Main class for managing the mouse-trajectory experiment."""
    def __init__(self):
        # The GUI is built on TKinter. First build the root for the application
        self.root = tk.Tk()
        self.root.title('Mouse experiment')
        self.root.resizable(False, False) #make window not resizable

        # Experiment variables to be set
        max_nr_paths = 15    # nr of paths to store
        max_training_nr = 5 # nr of training rounds
        self.experiment_settings = ExperimentSettings(max_nr_paths,
                                                      max_training_nr)

        self.experiment = None
        self.settings = None
        self.collection_status = None

    def start(self):
        """
        Run the experiment.

        Return a dataframe with paths, a dataframe with interpolated paths,
        and a dataframe with properties of the experiments.

        Stores recorded paths to a csv file.

        Stores path properties to a separate csv file.
        """

        #has_earlier_props = False
        has_earlier_paths = False
        last_trial_nr = -1
        user_settings = None

        has_earlier_props, df_props_old = read_old_properties()

        if has_earlier_props:
            last_trial_nr = int(df_props_old['trial'].max())
            user_settings = extract_user_settings(df_props_old)

        if os.path.isfile('paths.csv'):
            try:
                df_paths_old = pd.read_csv('paths.csv')
                has_earlier_paths = True
            except:
                pass

        # We will count how many paths for a given input method are
        # stored in the csv file
        nr_mouse_trials_collected = 0
        nr_trackpad_trials_collected = 0

        # The csv file also contains a column that records the how
        # manyieth path for that input method it is
        last_trackpad_trial_nr = -1
        last_mouse_trial_nr = -1

        # If a csv file exist, read this information out of the csv file
        if has_earlier_props and has_earlier_paths:
            mouse_trials = df_props_old[df_props_old['input_method'] == 1]
            last_mouse_trials = \
                mouse_trials['trial']\
                    .nlargest(self.experiment_settings.max_nr_paths)
            trackpad_trials = df_props_old[df_props_old['input_method'] == 0]
            last_trackpad_trials = \
                trackpad_trials['trial']\
                    .nlargest(self.experiment_settings.max_nr_paths)

            nr_mouse_trials_collected = \
                last_mouse_trials[last_mouse_trials >=
                                  self.experiment_settings.max_training_nr]\
                                  .count()
            nr_trackpad_trials_collected = \
                last_trackpad_trials[last_trackpad_trials >=
                                     self.experiment_settings.max_training_nr]\
                                     .count()

            if sum(df_props_old['input_method'] == 1) > 0:
                last_mouse_trial_nr = \
                    df_props_old[df_props_old['input_method'] == 1]\
                        ['trial_for_input_method'].max()
            if sum(df_props_old['input_method'] == 0) > 0:
                last_trackpad_trial_nr = \
                    df_props_old[df_props_old['input_method'] == 0]\
                        ['trial_for_input_method'].max()

        self.collection_status = CollectionStatus(nr_mouse_trials_collected,
                                                  nr_trackpad_trials_collected,
                                                  last_trackpad_trial_nr,
                                                  last_mouse_trial_nr,
                                                  last_trial_nr)

        # First collect data about these experiments in a dialog window
        self.settings = Settings(self.root, self.closed_settings,
                                 user_settings=user_settings)

        # The data collection happens through callbacks in a tkinter loop
        self.root.mainloop()

        # if list with dataframes is non empty
        if self.experiment and self.experiment.list_with_dataframes:
            # Concatenate all the dataframes from the different trials
            df = pd.concat(self.experiment.list_with_dataframes)

            columns = ['trial', 'trial_for_input_method']\
                      + UserSettings.accepted_keys\
                      + SystemSettings.accepted_keys\
                      + ['target_x',
                         'target_y',
                         'target_radius',
                         'delay']

            # convert the list with properties to a dataframe
            df_trial_props = pd.DataFrame(self.experiment.prop_list,
                                          columns=columns)

            # if there is earlier data available, then concatenate
            if has_earlier_props and has_earlier_paths:
                df = pd.concat([df_paths_old, df])
                df_trial_props = pd.concat([df_props_old, df_trial_props])

            # Only keep the last max_nr_paths of mouse-paths and max_nr_paths
            # of trackpad-paths
            mouse_trials = \
                df_trial_props[df_trial_props['input_method'] == 1]\
                    ['trial'].nlargest(self.experiment_settings.max_nr_paths)
            trackpad_trials = \
                df_trial_props[df_trial_props['input_method'] == 0]\
                    ['trial'].nlargest(self.experiment_settings.max_nr_paths)

            #This may not be the most efficient solution code surrounded
            # with possible timing option
            #timing_start = time.time()
            df = df[df['trial'].isin(mouse_trials)
                    | df['trial'].isin(trackpad_trials)]
            df_trial_props = \
                df_trial_props[df_trial_props['trial'].isin(mouse_trials)\
                               | df_trial_props['trial'].isin(trackpad_trials)]
            #print("Time spent selecting rows:", time.time() - timing_start)

            # Concatenate all interpolated paths
            df_int = pd.concat(self.experiment.interpolated_paths)

            # export path data to file
            df.to_csv('paths.csv', index=False) # Don't add column for index

            # Export the properties dataframe to a csv file
            df_trial_props.to_csv('paths_props.csv', index=False)

            # Return interpolated paths
            return df, df_int, df_trial_props

        return None, None, None

    def closed_settings(self, user_settings):
        """Destroy and clean up after settings window and start experiment."""
        # cleanup after the settings
        for child in self.root.winfo_children():
            child.destroy()

        # start the experiment
        self.experiment = Experiment(self.root, user_settings,
                                     self.experiment_settings,
                                     self.collection_status)

def read_old_properties():
    """Read in file with old properties.

    Returns:
    Boolean value to indicate whether the reading succeeded.
    Dataframe with previous experiment properties."""
    if os.path.isfile('paths_props.csv'):
        try:
            df_props_old = pd.read_csv('paths_props.csv')
            return True, df_props_old
        except:
            print('exception occured while reading old properties file')
    return False, None

def extract_user_settings(df_props_old):
    """Extract properties from a dataframe."""
    settings = \
        {'use_tue_laptop': int(df_props_old.iloc[-1]['use_tue_laptop']),
         'mouse_speed'   : int(df_props_old.iloc[-1]['mouse_speed']),
         'mouse_accuracy': int(df_props_old.iloc[-1]['mouse_accuracy']),
         'right_handed'  : int(df_props_old.iloc[-1]['right_handed']),
         'input_method'  : int(df_props_old.iloc[-1]['input_method']),
         'major'         : df_props_old.iloc[-1]['major'],
         'gender'        : df_props_old.iloc[-1]['gender']}
    if 'right_trackpad_handed' in df_props_old.columns:
        settings['right_trackpad_handed'] = int(df_props_old.iloc[-1]['right_trackpad_handed'])
    if 'right_mouse_handed' in df_props_old.columns:
        settings['right_mouse_handed'] = int(df_props_old.iloc[-1]['right_mouse_handed'])
    if 'trackpad_speed_set' in df_props_old.columns:
        settings['trackpad_speed_set'] = int(df_props_old.iloc[-1]['trackpad_speed_set'])
    user_settings = UserSettings(settings)
    return user_settings

class SystemSettingsReader:
    """Class to read system properties, such as properties of the mouse."""
    def __init__(self, root):
        # default values for system settings
        self._root = root

        _system_settings = \
            {'touchpad_speed' : -1,
             'touchpad_honor' : -1,
             'mouse_speed_rec' : -1,
             'mouse_threshold_1' : -1,
             'mouse_threshold_2' : -1,
             'mouse_acceleration' : -1,
             'platform' : platform.system(),
             'platform_version' : platform.release(),
             'screen_width': root.winfo_screenwidth(),
             'screen_height': root.winfo_screenheight()}

        self._system_settings = SystemSettings(_system_settings)

        self.in_windows_10 = False
        if (os.name == 'nt') and (platform.release() == '10'):
            self.in_windows_10 = True

            try:
                # Find out which touchpad properties can be read from registry
                a_reg = ConnectRegistry(None, HKEY_CURRENT_USER)
                a_key = OpenKey(a_reg,\
                r"Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad")

                key_info = QueryInfoKey(a_key)

                value_list = [EnumValue(a_key, _)[0]
                              for _ in range(key_info[1])]

                candidate_keys = ['CursorSpeed',
                                  'HonorMouseAccelSetting']

                self.keys_to_read = [_ for _ in candidate_keys if
                                     _ in value_list]

                CloseKey(a_key)
            except OSError as err:
                print('Exception occurred when reading cursorspeed: ', err)
            except:
                print(('Unexpected error occurred when '
                       'listing touchpad variables from registry: '),
                      sys.exc_info()[0])

    def extract_mouse_props_windows(self):
        """Read out touchpad and mouse parameters in Windows."""
        try:
            # Read touchpad speed from Windows registry
            a_reg = ConnectRegistry(None, HKEY_CURRENT_USER)
            a_key = OpenKey(a_reg,\
            r"Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad")
            #mouse_properties = {}
            if 'CursorSpeed' in self.keys_to_read:
                self._system_settings['touchpad_speed'] = \
                int(QueryValueEx(a_key, 'CursorSpeed')[0])
            if 'HonorMouseAccelSetting' in self.keys_to_read:
                self._system_settings['touchpad_honor'] = \
                QueryValueEx(a_key, 'HonorMouseAccelSetting')[0]
            CloseKey(a_key)
        except OSError as err:
            print('Exception occurred when reading cursorspeed: ', err)

        try:
            # Get information on the mouse
            get_mouse_speed = 112
            speed = ctypes.c_int()
            windll.user32.SystemParametersInfoA(get_mouse_speed, 0,
                                                ctypes.byref(speed), 0)
            self._system_settings['mouse_speed_rec'] = speed.value

            int_3_array_type = ctypes.c_int * 3
            result = int_3_array_type()
            get_mouse = 3
            windll.user32.SystemParametersInfoA(get_mouse, 0,
                                                ctypes.byref(result), 0)
            self._system_settings['mouse_threshold_1'] = result[0]
            self._system_settings['mouse_threshold_2'] = result[1]
            self._system_settings['mouse_acceleration'] = result[2]

        except OSError as err:
            print('Exception occurred when reading mouse properties ', err)
        except:
            print(('Unexpected error occurred when '
                   'reading mouse properties'),
                  sys.exc_info()[0])
        return self._system_settings

    def extract_mouse_properties(self):
        """Read out touchpad and mouse parameters in Windows."""
        if self.in_windows_10:
            self.extract_mouse_props_windows()
        self._system_settings['screen_width'] = self._root.winfo_screenwidth()
        self._system_settings['screen_height'] = \
            self._root.winfo_screenheight()
        return self._system_settings

# Various samplers as generators, to use for randomly selecting parameters
# in the experiment
def regular_orientation_sampler(N):
    """Generate random angles in N discrete steps between 0 and 2 pi."""
    while True:
        yield 2 * math.pi * random.randrange(N) / N

def choice_sampler(choices):
    """Generate random choice from the list choices"""
    while True:
        yield random.choice(choices)

def uniform_sampler(minimum, maximum):
    """Generate samples from uniform distribution between minimum and maximum.
    """
    while True:
        yield random.uniform(minimum, maximum)

def range_sampler(start, stop):
    """Generate random samples from start (inclusive) to stop (non-inclusive).
    """
    while True:
        yield random.randrange(start, stop)

class ExperimentSettings:
    """Wrapper class to organize experiment settings."""
    def __init__(self, max_nr_paths, max_training_nr):
        self.max_nr_paths = max_nr_paths
        self.max_training_nr = max_training_nr

class UserSettings(dict):
    """Wrapper class for storage of user settings."""
    accepted_keys = ['use_tue_laptop',
                     'input_method',
                     'mouse_speed',
                     'mouse_accuracy',
                     'trackpad_speed_set',
                     'right_handed',
                     'right_mouse_handed',
                     'right_trackpad_handed',
                     'major',
                     'gender']

class SystemSettings(dict):
    """Wrapper class for storage of system settings."""
    accepted_keys = ['touchpad_speed',
                     'touchpad_honor',
                     'mouse_speed_rec',
                     'mouse_threshold_1',
                     'mouse_threshold_2',
                     'mouse_acceleration',
                     'platform',
                     'platform_version',
                     'screen_width',
                     'screen_height']

class CollectionStatus:
    """Wrapper class to store status of experiment from old properties file."""
    def __init__(self, nr_mouse_trials_collected,
                 nr_trackpad_trials_collected,
                 last_trackpad_trial_nr,
                 last_mouse_trial_nr,
                 last_trial_nr):
        self.nr_mouse_trials_collected = nr_mouse_trials_collected
        self.nr_trackpad_trials_collected = nr_trackpad_trials_collected
        self.last_trackpad_trial_nr = last_trackpad_trial_nr
        self.last_mouse_trial_nr = last_mouse_trial_nr
        self.last_trial_nr = last_trial_nr

class Experiment:
    """Class to manage the experiment."""
    def __init__(self, root,
                 user_settings,
                 experiment_settings,
                 collection_status):
        self.root = root

        self._user_settings = user_settings
        self.settings_reader = SystemSettingsReader(root)

        self.input_method = user_settings['input_method']

        self.max_nr_paths = experiment_settings.max_nr_paths
        self.trial = collection_status.last_trial_nr + 1
        self.max_training_nr = experiment_settings.max_training_nr
        self.job = None
        self.nr_mouse_trials_collected = \
            collection_status.nr_mouse_trials_collected
        self.nr_trackpad_trials_collected = \
            collection_status.nr_trackpad_trials_collected
        if self.input_method == 0:
            self.trackpad_trial_nr = collection_status.last_trackpad_trial_nr \
                                     + 1
        else:
            self.mouse_trial_nr = collection_status.last_mouse_trial_nr + 1

        self.start_time = time.perf_counter()
        #self.trial = 0                         # initial trial number
        self.list_with_dataframes = []          # list to store recorded paths
        self.interpolated_paths = []            # list to store processed paths
        self.prop_list = []                     # list to store properties
                                                # of experiment
        self.mouse_list = []
        self.collect_data = False               # flag whether mouse data
                                                # should be collected
        self.experiment_scheduled = False       # flag whether experiment
                                                # is scheduled
        self.use_right_hand = True              # flag whether
                                                # right hand is used
        self.target_radius = 3                  # target radius in pixels
        self.delay = 2000                       # delay between moving mouse on
                                                # red square and appearance of
                                                # target

        self.window_size = 700

        self.target_x = 0
        self.target_y = 0

        # The experiment can be customized by choosing the desired
        # samplers for the orientation and distance of the target to the
        # center, and the radius of the target
        self.orientation_sampler = regular_orientation_sampler(8)
        self.radius_sampler = choice_sampler([3, 6, 9])
        self.distance_sampler = uniform_sampler(100, self.window_size/2-60)
        self.delay_sampler = range_sampler(2000, 4000)

        self.schedule_time = time.perf_counter()
        self.x_origin = self.window_size // 2
        self.y_origin = self.window_size // 2

        # add a frame to the root
        self.frame = tk.Frame(self.root, width=self.window_size,
                              height=self.window_size)

        # add a canvas to the frame
        self.w = tk.Canvas(self.root, width=self.window_size,
                           height=self.window_size, bg="white")
        self.w.pack()

        # draw items on the canvas and record their ids assigned by tkinter
        self.middle_id = self.w.create_rectangle(self.x_origin - 5,
                                                 self.y_origin - 5,
                                                 self.x_origin + 5,
                                                 self.y_origin + 5, fill="red")
        self.text_id = self.w.create_text(self.x_origin,
                                          self.window_size - 30,
                                          text=("Move your mouse "
                                                "to the red square"),
                                          anchor="s")

        if self.trial <= self.max_training_nr:
            self.counter_id = self.w.create_text(self.x_origin, 20,\
                text="Let's have some training rounds first",\
                anchor="c")
        else:
            self.counter_id = self.w.create_text(self.x_origin,
                                                 20, text=self.counter_text(),
                                                 anchor="c")

        # Later we will draw a blue dot. We will use the self.target_id
        # constant to store the id of the blue dot assigned by tkinter
        self.target_id = None

        # Add event listeners
        self.root.bind('<Motion>', self.motion)
        self.root.bind('<Button-1>', self.click)

    def counter_text(self):
        """Format text with counters of trackpad and mouse trials."""
        return ("Paths collected:      Trackpad: {:d}/{:d}      "
                "Mouse: {:d}/{:d}")\
            .format(min(self.nr_trackpad_trials_collected, self.max_nr_paths),
                    self.max_nr_paths,
                    min(self.nr_mouse_trials_collected, self.max_nr_paths),
                    self.max_nr_paths)

    def start_experiment(self):
        """Make target appear, reset time to zero, and start recording."""
        # Check that mouse is still on red square
        if not self.middle_id in self.w.find_withtag(tk.CURRENT):
            # If not, instruct the user to keep mouse on red square
            self.w.itemconfigure(self.text_id,
                                 text=("Keep your mouse on the red square to "
                                       "start the experiment"))
            return

        self.job = None

        # the delay is time difference between first time scheduled
        self.delay = time.perf_counter() - self.schedule_time

        self.mouse_list = []                 # clear list with mouse data
        self.collect_data = True             # set collect data flag to true

        # change instruction text
        if self.trial <= self.max_training_nr:
            self.w.itemconfigure(self.text_id, text="Click the blue dot!")
        else:
            self.w.itemconfigure(self.text_id, text="")

        # choose a random position for the target using polar coordinates
        random_r = next(self.distance_sampler)
        random_phi = next(self.orientation_sampler)

        self.target_x = round(random_r * math.cos(random_phi))
        self.target_y = round(random_r * math.sin(random_phi))

        # convert to the correct coordinates on the canvas
        x_gr = self.x_origin + random_r * math.cos(random_phi)
        y_gr = self.y_origin - random_r * math.sin(random_phi)

        # select a new target radius
        self.target_radius = next(self.radius_sampler)

        # create blue dot
        self.target_id = self.w.create_oval(x_gr-self.target_radius,
                                            y_gr-self.target_radius,
                                            x_gr+self.target_radius,
                                            y_gr+self.target_radius,
                                            fill="blue")

        # the root of the window in the coordinates of the screen
        w_x = self.root.winfo_rootx()
        w_y = self.root.winfo_rooty()

        # the current coordinates of the mouse, in coordinates of the screen
        p_x = self.root.winfo_pointerx()
        p_y = self.root.winfo_pointery()

        # the coordinates of the mouse, in window coordinates
        x_win = p_x - w_x
        y_win = p_y - w_y

        # the position of the canvas in window coordinates
        c_x = self.w.winfo_x()
        c_y = self.w.winfo_y()

        # the coordinates of the mouse,
        # now with y axis up and origin at red square
        x = x_win - self.x_origin - c_x
        y = - y_win + self.y_origin + c_y

        # add the current coordinate as the
        # first item in the list of coordinates
        self.start_time = time.perf_counter()
        self.mouse_list.append([self.trial, 0, x, y])

    def motion(self, event):
        """
        Callback function if mouse is moved.

        It has two purposes: if the mouse moves on the red square, and
        no trial has been scheduled yet, a trial will be scheduled

        If an experiment is running, this function will record the coordinates
        of the mouse
        """
        # get window coordinates of mouse position corresponding to event
        x_win, y_win = event.x, event.y
        # p_x = self.root.winfo_pointerx()
        # p_y = self.root.winfo_pointery()
        # there may be a small difference between these values

        # If the mouse is on the red square, and no experiment has been
        # scheduled yet, then it should be scheduled now
        if self.w.find_withtag(tk.CURRENT) and (not self.experiment_scheduled):
            if self.middle_id in self.w.find_withtag(tk.CURRENT):

                # choose a delay after which the experiment should start
                self.delay = next(self.delay_sampler)

                # schedule the experiment
                self.job = self.root.after(self.delay, self.start_experiment)
                # flag that experiment has been scheduled
                self.experiment_scheduled = True
                # record the time at which the experiment was scheduled
                self.schedule_time = time.perf_counter()

                # Update counters
                if self.trial < self.max_training_nr:
                    self.w.itemconfigure(self.counter_id,
                                         text="Training: {:d}/{:d}"\
                                         .format(self.trial+1,
                                                 self.max_training_nr))

                    # update instruction text
                    self.w.itemconfigure(self.text_id,
                                         text="Wait for blue dot to appear...")

                elif self.trial == self.max_training_nr:
                    self.w.itemconfigure(self.counter_id,
                                         text=self.counter_text())

                else:
                    # update instruction text
                    self.w.itemconfigure(self.text_id, text="")

        if (self.middle_id not in self.w.find_withtag(tk.CURRENT))\
          and self.job:
            self.w.itemconfigure(self.text_id,
                                 text=("Keep your mouse on the red square to "
                                       "start the experiment"))
            self.root.after_cancel(self.job)
            self.experiment_scheduled = False
            self.job = None

        # if an experiment is running, i.e. if data is being collected...
        if self.collect_data:
            # convert to coordinates with middle square in origin
            x = x_win - self.x_origin
            y = - y_win + self.y_origin
            # add trial number, time, and coordinates to mouse_list
            self.mouse_list.append([self.trial,
                                    time.perf_counter()-self.start_time,
                                    x, y])

    def click(self, event):
        """
        Callback function for clicks of the mouse.

        If the click is on the target, the current trial will be stopped,
        and properties of the trial will be appended to the properties list.
        """
        # If the click is on the target...
        if self.w.find_withtag(tk.CURRENT):
            if self.target_id in self.w.find_withtag(tk.CURRENT):
                # record final mouse position
                x = event.x - self.x_origin
                y = -event.y + self.y_origin
                self.mouse_list.append([self.trial,
                                        time.perf_counter() - self.start_time,
                                        x, y])

                # update instruction text
                self.w.itemconfigure(self.text_id, text="You did it!")
                # convert the whole mouse_list in a dataframe
                # (we are first working with lists for efficiency reasons)
                df = pd.DataFrame(self.mouse_list,
                                  columns=['trial', 't', 'x', 'y'])
                # store the dataframe in a list
                self.list_with_dataframes.append(df)
                # for post-processing, send the dataframe with paths to a
                # function that processes them
                self.interpolated_paths.append(self.interpolate(df))

                if self.input_method == 0:
                    trial_for_input_method = self.trackpad_trial_nr
                else:
                    trial_for_input_method = self.mouse_trial_nr

                mouse_props = self.settings_reader.extract_mouse_properties()

                # collect all properties to store in one list
                props = [self.trial,
                         trial_for_input_method]\
                      + [self._user_settings[_] \
                         for _ in UserSettings.accepted_keys]\
                      + [mouse_props[_] \
                         for _ in SystemSettings.accepted_keys]\
                      + [self.target_x,
                         self.target_y,
                         self.target_radius,
                         self.delay]

                # append the properties of the experiment to the prop_list
                self.prop_list.append(props)

                # clear the mouse list
                self.mouse_list = []
                # flag that the experiment has stopped
                self.collect_data = False
                # flag that no experiment is scheduled
                self.experiment_scheduled = False
                # delete the target from the screen
                self.w.delete(self.target_id)
                # update instruction to user
                self.w.itemconfigure(self.text_id,\
                    text="Move your mouse back to the red square")
                # update the trial number
                self.trial += 1

                if self.input_method == 0:
                    self.trackpad_trial_nr += 1
                else:
                    self.mouse_trial_nr += 1

                if self.trial > self.max_training_nr:
                    if self.input_method == 0:
                        self.nr_trackpad_trials_collected += 1
                    else:
                        self.nr_mouse_trials_collected += 1

                    self.w.itemconfigure(self.counter_id,
                                         text=self.counter_text())
                    if (self.input_method == 0) and\
                        (self.nr_trackpad_trials_collected ==\
                            self.max_nr_paths):
                        if self.nr_mouse_trials_collected < self.max_nr_paths:
                            messagebox.showinfo("Trackpad paths finished",\
                                ("You have collected enough paths using a "
                                 "trackpad. It would be helpful if you could "
                                 "restart the application and collect more "
                                 "paths with a mouse."))
                        else:
                            messagebox.showinfo("All done!",\
                                ("You have collected the required number "
                                 "of paths. You can keep drawing paths, "
                                 "previously recorded paths will then be "
                                 "overwritten."))
                    if (self.input_method == 1) and\
                        (self.nr_mouse_trials_collected == self.max_nr_paths):
                        if self.nr_trackpad_trials_collected\
                            < self.max_nr_paths:
                            messagebox.showinfo("Mouse paths finished",\
                                ("You have collected enough paths using a "
                                 "mouse. Please restart the application and "
                                 "collect some more paths with a trackpad."))
                        else:
                            messagebox.showinfo("All done!",\
                                ("You have collected the required number of "
                                 "paths. You can keep drawing paths, "
                                 "previously recorded paths will then be "
                                 "overwritten."))
                elif self.trial == self.max_training_nr:
                    self.w.itemconfigure(self.counter_id,\
                        text="Training completed! Now let's collect data")
                    messagebox.showinfo("Training completed!",\
                        "Training completed! Now let's collect some data.")
                # update nr of trials collected
            else:
                if not self.experiment_scheduled:
                    self.w.itemconfigure(self.text_id,\
                        text=("First move your mouse to the red square "
                              "to start an experiment"))
                elif not self.job:
                    self.w.itemconfigure(self.text_id, text="Miss!")
        else:
            if not self.experiment_scheduled:
                self.w.itemconfigure(self.text_id,\
                    text=("First move your mouse to the red square "
                          "to start an experiment"))
            elif not self.job:
                self.w.itemconfigure(self.text_id, text="Miss!")

    def interpolate(self, df):
        """Create dataframe with interpolated paths from dataframe with paths.
        """
        t = df['t']
        x = df['x']
        y = df['y']

        # create interpolation functions
        f_x = interp1d(t, x, kind='linear')
        f_y = interp1d(t, y, kind='linear')

        # create sequence of times increasing in ms
        new_t = range(math.ceil(np.min(t)*1000), math.ceil(np.max(t)*1000))
        new_t_old = [0.001 * s for s in new_t]

        # determine interpolated coordinates for those times
        new_x = f_x(new_t_old)
        new_y = f_y(new_t_old)

        se_trial = [self.trial] * len(new_t)

        return pd.DataFrame({'trial': se_trial,
                             't':new_t_old, 'x':new_x, 'y':new_y})


class Settings:
    """Class for creating and managing the user input form."""
    def __init__(self, parent, callback, user_settings=None):
        self.parent = parent
        self.callback = callback

        self.v_major = tk.StringVar()
        self.v_major.set('Please choose your major')

        self.v_use_tue_laptop = tk.IntVar()
        self.v_use_tue_laptop.set(-1)

        self.v_mouse_speed = tk.IntVar()
        self.v_mouse_speed.set(-1)
        
        self.v_trackpad_speed = tk.IntVar()
        self.v_trackpad_speed.set(-1)

        self.v_mouse_accuracy = tk.IntVar()
        self.v_mouse_accuracy.set(-1)

        self.v_handed = tk.IntVar()
        self.v_handed.set(-1)

        self.v_trackpad_hand = tk.IntVar()
        self.v_trackpad_hand.set(-1)
        
        self.v_mouse_hand = tk.IntVar()
        self.v_mouse_hand.set(-1)

        self.v_input_method = tk.IntVar()
        self.v_input_method.set(-1)

        self.v_gender = tk.IntVar()
        self.v_gender.set(-1)

        self.next_trial_nr = 0

        if user_settings:
            self.v_use_tue_laptop.set(user_settings['use_tue_laptop'])
            self.v_mouse_speed.set(user_settings['mouse_speed'])
            self.v_mouse_accuracy.set(user_settings['mouse_accuracy'])
            self.v_handed.set(user_settings['right_handed'])
            if 'right_trackpad_handed' in user_settings.keys():
                self.v_trackpad_hand.set(user_settings['right_trackpad_handed'])
            if 'right_mouse_handed' in user_settings.keys():
                self.v_mouse_hand.set(user_settings['right_mouse_handed'])
            if 'trackpad_speed_set' in user_settings.keys():
                self.v_trackpad_speed.set(user_settings['trackpad_speed_set'])
            self.v_input_method.set(user_settings['input_method'])
            self.v_major.set(user_settings['major'])
            self.v_gender.set(user_settings['gender'])

        self.body(parent)

    def changed_use_tue_laptop(self):
        """Change settings input form when user toggles usage of tue laptop."""
        value = self.v_use_tue_laptop.get()
        if value == 1:
            for x in [self.i1, self.i2, self.i3, self.i4, self.i5, self.i6]:
                x.grid()
        else:
            for x in [self.i1, self.i2, self.i3, self.i4, self.i5, self.i6]:
                x.grid_remove()

    def body(self, parent):
        """Arrange the form with user settings."""
        master = tk.Frame(parent, padx=20, pady=20)
        master.pack()

        row = 0
        tk.Label(master, text="Please answer the following questions:")\
            .grid(row=row, columnspan=3, sticky='W', pady=10)

        row += 1
        tk.Label(master, text="What is your major?").grid(row=row, sticky='W')
        option = tk.OptionMenu(master, self.v_major,
                               'Industrial Engineering',
                               'Innovation Sciences',
                               'Applied Physics',
                               'Mechanical Engineering',
                               'Electrical Engineering',
                               'Biomedical Engineering',
                               'Built Environment',
                               'Industrial Design',
                               'Chemical Engineering and Chemistry',
                               'Computer Science',
                               'Data Science',
                               'Applied Mathematics',
                               'Other')
        option.grid(row=row, column=1, columnspan=2, sticky='EW')

        row += 1
        tk.Label(master, text="What is your gender?").grid(row=row, sticky='W')
        tk.Radiobutton(master, text="Male", variable=self.v_gender, value=0)\
            .grid(row=row, column=1, sticky='W')
        tk.Radiobutton(master, text="Female", variable=self.v_gender, value=1)\
            .grid(row=row, column=2, sticky='W')
        tk.Radiobutton(master, text="Other", variable=self.v_gender, value=2)\
            .grid(row=row, column=3, sticky='W')

        row += 1
        tk.Label(master, text="Which hand do you use to write?")\
            .grid(row=row, sticky='W')
        self.b1 = tk.Radiobutton(master, text="Left", \
                                 variable=self.v_handed, value="0")\
                                 .grid(row=row, column=1, sticky='W')
        tk.Radiobutton(master, text="Right", variable=self.v_handed, value="1")\
            .grid(row=row, column=2, sticky='W')

        row += 1
        tk.Label(master, text="With which hand do you normally use the trackpad?")\
            .grid(row=row, sticky='W')
        self.b1 = tk.Radiobutton(master, text="Left", \
                                 variable=self.v_trackpad_hand, value="0")\
                                 .grid(row=row, column=1, sticky='W')
        tk.Radiobutton(master, text="Right", variable=self.v_trackpad_hand, value="1")\
            .grid(row=row, column=2, sticky='W')
            
        row += 1
        tk.Label(master, text="With which hand do you normally use the mouse?")\
            .grid(row=row, sticky='W')
        self.b1 = tk.Radiobutton(master, text="Left", \
                                 variable=self.v_mouse_hand, value="0")\
                                 .grid(row=row, column=1, sticky='W')
        tk.Radiobutton(master, text="Right", variable=self.v_mouse_hand, value="1")\
            .grid(row=row, column=2, sticky='W')

        row += 1
        tk.Label(master, text="Do you use a TU/e laptop?")\
            .grid(row=row, sticky='W')
        tk.Radiobutton(master, text="Yes", variable=self.v_use_tue_laptop,
                       value='1', command=self.changed_use_tue_laptop)\
                       .grid(row=row, column=1, sticky='W')
        tk.Radiobutton(master, text="No", variable=self.v_use_tue_laptop,
                       value='0', command=self.changed_use_tue_laptop)\
                       .grid(row=row, column=2, sticky='W')

        row += 1
        self.i1 = tk.Label(master, text="Set mouse speed to medium (10)")
        self.i1.grid(row=row, sticky='W')
        self.i2 = tk.Checkbutton(master, text="", variable=self.v_mouse_speed)
        self.i2.grid(row=row, column=1, sticky='W')

        row += 1
        self.i3 = tk.Label(master, text="Set the mouse accuracy to enhanced")
        self.i3.grid(row=row, sticky='W')
        self.i4 = tk.Checkbutton(master, text="",
                                 variable=self.v_mouse_accuracy)
        self.i4.grid(row=row, column=1, sticky='W')

        row += 1
        self.i5 = tk.Label(master, text="Set trackpad speed to medium (5)")
        self.i5.grid(row=row, sticky='W')
        self.i6 = tk.Checkbutton(master, text="", variable=self.v_trackpad_speed)
        self.i6.grid(row=row, column=1, sticky='W')

        

        row += 1
        tk.Label(master, text="Will you use a trackpad or a mouse?")\
            .grid(row=row, sticky='W')
        tk.Radiobutton(master, text="Trackpad", variable=self.v_input_method,
                       value=0)\
                       .grid(row=row, column=1, sticky='W')
        tk.Radiobutton(master, text="Mouse", variable=self.v_input_method,
                       value=1)\
                       .grid(row=row, column=2, sticky='W')

        row += 1
        tk.Label(master,
                 text="Please use the hand you normally use for this input device")\
                 .grid(row=row, columnspan=4, sticky='W')

        row += 1
        box = tk.Frame(master, pady=10)
        box.grid(row=row, column=0, columnspan=3)

        _w = tk.Button(box, text="OK", width=10, command=self.ok,
                       default=tk.ACTIVE)
        _w.pack(side=tk.LEFT, padx=5, pady=5)
        _w = tk.Button(box, text="Cancel", width=10, command=self.cancel)
        _w.pack(side=tk.LEFT, padx=5, pady=5)

        row += 1
        self.error_label = tk.Label(master, text="", fg="red")
        self.error_label.grid(row=row, columnspan=3, sticky="we")

        # initially hide the mouse options (until a selection is made)
        self.changed_use_tue_laptop()

        master.rowconfigure(4, weight=3)

        return self.b1 # initial focus

    def ok(self):
        """Process form for when user presses 'ok'."""
        handed = self.v_handed.get()
        right_trackpad_handed = self.v_trackpad_hand.get()
        right_mouse_handed = self.v_mouse_hand.get()
        use_tue_laptop = self.v_use_tue_laptop.get()
        mouse_speed = self.v_mouse_speed.get()
        trackpad_speed = self.v_trackpad_speed.get()
        mouse_accuracy = self.v_mouse_accuracy.get()
        input_method = self.v_input_method.get()
        major = self.v_major.get()
        gender = self.v_gender.get()

        # validate the input (make sure that the required fields are filled in)
        if handed == -1 or right_trackpad_handed ==-1 or right_mouse_handed==-1 or use_tue_laptop == -1 or gender == -1\
          or major == 'Please choose your major' or input_method == -1:
            self.error_label.config(text="Please fill in all the fields.")
            return

        if use_tue_laptop == 1 and (mouse_speed < 1 or mouse_accuracy < 1 or trackpad_speed < 1):
            self.error_label.config(text="Please verify your mouse settings.")
            return

        settings = {
            'right_handed'   : handed,
            'right_trackpad_handed' : right_trackpad_handed,
            'right_mouse_handed' : right_mouse_handed,
            'use_tue_laptop' : use_tue_laptop,
            'mouse_speed'    : mouse_speed,
            'trackpad_speed_set' : trackpad_speed,
            'mouse_accuracy' : mouse_accuracy,
            'input_method'   : input_method,
            'major'          : major,
            'gender'         : gender
        }
        user_settings = UserSettings(settings)
        self.callback(user_settings)

    def cancel(self):
        """Exit for when user presses 'cancel'."""
        self.parent.destroy()

if __name__ == '__main__':
    experiment = MouseExperiment()
    experiment.start()
