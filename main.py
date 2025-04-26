"""
This file contains code for the application "Gemini AI App Store".
Author: SoftwareApkDev
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import threading
import queue

# --- Configuration ---

# Replace with your actual PyPi package name!
# When you package this app store itself, this name should match your setup.py/pyproject.toml
APP_STORE_PACKAGE_NAME = "gemini_ai_app_store"

# Define the apps available in the store
# Format: {"Display Name": {"package_name": "pypi-package-name", "module_name": "module_to_run_with_python_m"}}
# module_name is optional if the app is just a library, but required to "Run" it.

AVAILABLE_APPS = {
    # Example: A hypothetical Gemini Chat app distributed as 'gemini_chat_app' on PyPi
    # and runnable with 'python -m gemini_chat_app'
    "Gemini Chat App": {"package_name": "gemini_chat_app", "module_name": "gemini_chat_app"},
    "Gemini Geometry Wars": {"package_name": "gemini_geometry_wars", "module_name": "gemini_geometry_wars"},
    # Add more Gemini-integrated apps here.
    # REMEMBER: These package_names must exist on PyPi, and module_names must be runnable.
}

# --- Helper Functions ---

class CommandRunner:
    """Helper to run commands in a separate thread and update the GUI safely."""
    def __init__(self, output_queue, log_callback, enable_buttons_callback):
        self.output_queue = output_queue
        self.log_callback = log_callback
        self.enable_buttons_callback = enable_buttons_callback
        self._stop_event = threading.Event()
        self._current_process = None # Keep track of the current process if needed

    def run_command(self, command, package_name):
        """Runs a command in a subprocess and puts output/result in the queue."""
        self.output_queue.put(f"--> Running command: {' '.join(command)}\n")
        process = None
        try:
            # Use shell=True on Windows for .bat, .cmd files, but generally avoid it.
            # Here we are running python -m, which doesn't need shell=True.
            # Using text=True is preferred over universal_newlines=True in newer Python.
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self._current_process = process # Store the process

            # Read stdout and stderr in real-time
            # This loop can block if the process produces a lot of output and the pipe fills up
            # For robustness, especially with long-running outputs, consider using select/poll
            # or separate threads for stdout/stderr, but this is sufficient for typical pip output.
            while True:
                stdout_line = process.stdout.readline()
                stderr_line = process.stderr.readline()

                # Check if process has exited and pipes are empty
                if not stdout_line and not stderr_line and process.poll() is not None:
                    break

                if stdout_line:
                    self.output_queue.put(stdout_line)
                if stderr_line:
                    self.output_queue.put(f"[ERROR] {stderr_line}") # Differentiate errors

                # Small sleep to prevent a tight loop from consuming CPU if pipes are empty
                if not stdout_line and not stderr_line:
                     threading.sleep(0.01)

                # Check stop event if you want to be able to cancel commands
                # if self._stop_event.is_set():
                #     if process and process.poll() is None:
                #         process.terminate() # or process.kill()
                #     self.output_queue.put(("[CANCELLED]", package_name, -1))
                #     return

            rc = process.wait() # Wait for the process to finish after pipes are read
            self.output_queue.put(f"<-- Command finished with return code: {rc}\n")
            self.output_queue.put(("DONE", package_name, rc)) # Signal command completion

        except FileNotFoundError:
            self.output_queue.put(f"[ERROR] Command not found. Make sure Python and pip are in your PATH.\n")
            self.output_queue.put(("DONE", package_name, 1)) # Signal failure
        except Exception as e:
            self.output_queue.put(f"[ERROR] An unexpected error occurred: {e}\n")
            self.output_queue.put(("DONE", package_name, 1)) # Signal failure
        finally:
            self._current_process = None # Clear the stored process
            # Ensure buttons are re-enabled even if there's an exception within the thread
            self.output_queue.put(("FINISH_THREAD", None, None))


# --- GUI Application ---

class GeminiAppStore(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Gemini App Store")
        self.geometry("900x720")

        self.output_queue = queue.Queue()
        self.command_runner = CommandRunner(self.output_queue, self.log_message, self.enable_buttons)

        self._setup_widgets()
        self._populate_app_list()
        self._process_queue() # Start checking the queue for updates

    def _setup_widgets(self):
        # Frame for the listbox and scrollbar
        list_frame = ttk.Frame(self)
        list_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.app_listbox = tk.Listbox(list_frame, width=50, height=10, selectmode=tk.SINGLE) # Use SINGLE select mode
        self.app_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.app_listbox.bind('<<ListboxSelect>>', self._on_listbox_select)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.app_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.app_listbox.config(yscrollcommand=scrollbar.set)

        # Frame for buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)

        self.install_button = ttk.Button(button_frame, text="Install Selected", command=self._start_install_selected, state=tk.DISABLED)
        self.install_button.grid(row=0, column=0, padx=5)

        self.uninstall_button = ttk.Button(button_frame, text="Uninstall Selected", command=self._start_uninstall_selected, state=tk.DISABLED)
        self.uninstall_button.grid(row=0, column=1, padx=5)

        self.run_button = ttk.Button(button_frame, text="Run Selected", command=self._start_run_selected, state=tk.DISABLED)
        self.run_button.grid(row=0, column=2, padx=5)

        # Output area
        output_frame = ttk.LabelFrame(self, text="Output")
        output_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # Adding a scrollbar to the output text area
        output_scrollbar = ttk.Scrollbar(output_frame, orient=tk.VERTICAL)
        self.output_text = tk.Text(output_frame, height=8, state=tk.DISABLED, yscrollcommand=output_scrollbar.set)
        output_scrollbar.config(command=self.output_text.yview)

        output_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)


    def _populate_app_list(self):
        """Populates the listbox with available app display names."""
        for display_name in AVAILABLE_APPS:
            self.app_listbox.insert(tk.END, display_name)

    def _on_listbox_select(self, event):
        """Enable buttons when an item is selected."""
        selected_indices = self.app_listbox.curselection()
        if selected_indices:
            self.enable_buttons()
        else:
            self.disable_buttons()

    def disable_buttons(self):
        """Disables all action buttons."""
        self.install_button.config(state=tk.DISABLED)
        self.uninstall_button.config(state=tk.DISABLED)
        self.run_button.config(state=tk.DISABLED)

    def enable_buttons(self):
        """Enables buttons if an item is selected."""
        selected_indices = self.app_listbox.curselection()
        if selected_indices:
            self.install_button.config(state=tk.NORMAL)
            self.uninstall_button.config(state=tk.NORMAL)
            self.run_button.config(state=tk.NORMAL)
        else:
             self.disable_buttons() # Should already be disabled, but good practice

    def log_message(self, message):
        """Appends a message to the output text area."""
        self.output_text.config(state=tk.NORMAL)
        # Ensure message ends with newline if it doesn't already
        if not message.endswith('\n'):
             message += '\n'
        self.output_text.insert(tk.END, message)
        self.output_text.see(tk.END) # Auto-scroll to the bottom
        self.output_text.config(state=tk.DISABLED)

    def _get_selected_app_info(self):
        """Gets the package and module name for the selected app."""
        selected_indices = self.app_listbox.curselection()
        if not selected_indices:
            self.log_message("Please select an application first.\n")
            return None, None, None

        index = selected_indices[0]
        display_name = self.app_listbox.get(index)
        app_info = AVAILABLE_APPS.get(display_name)

        if app_info:
            # Ensure package_name is always present
            package_name = app_info.get("package_name")
            if not package_name:
                 self.log_message(f"[ERROR] Configuration error: 'package_name' missing for '{display_name}'.\n")
                 return None, None, None
            module_name = app_info.get("module_name") # module_name might be optional if only installing
            return display_name, package_name, module_name
        else:
            self.log_message(f"Error: Could not find info for selected app: {display_name}\n")
            return None, None, None

    def _start_install_selected(self):
        """Initiates the installation process in a separate thread."""
        display_name, package_name, _ = self._get_selected_app_info()
        if package_name:
            self.log_message(f"Attempting to install: {display_name} ({package_name})\n")
            self.disable_buttons()

            # Create a thread to run the installation commands
            thread = threading.Thread(target=self._install_app, args=(package_name,))
            thread.daemon = True # Allow the main thread to exit even if this is running
            thread.start()

    def _install_app(self, target_package):
        """Installs the app store itself, then the target app."""
        # Step 1: Ensure the app store is installed/upgraded from PyPi
        # This ensures the user has the latest version of the store itself.
        self.log_message(f"Ensuring {APP_STORE_PACKAGE_NAME} is installed/upgraded from PyPi...\n")
        # Use --break-system-packages if needed on Python 3.11+ in virtual environments
        # where the venv might "inherit" global site-packages
        # Add --user if installing outside a venv and without root, though venv is recommended
        store_install_command = [sys.executable, '-m', 'pip', 'install', '--upgrade', APP_STORE_PACKAGE_NAME]
        if sys.version_info >= (3, 11):
             # Add --break-system-packages for newer Python versions in certain environments
             # This might be needed if installing into a venv that copies system packages
             # Use with caution. Alternatively, ensure you are in a clean venv.
             # store_install_command.append('--break-system-packages')
             pass # Not adding by default, user should manage environment

        # Run the store install command and wait for its completion signal from the runner
        self.command_runner.run_command(store_install_command, f"STORE_{APP_STORE_PACKAGE_NAME}") # Use a unique identifier for the queue signal

        store_install_success = False
        # Wait for the store install command to finish signal in the queue
        # A more robust approach would track command IDs, but this simple loop works
        # for sequential commands where the next step depends on the previous one's result.
        while True:
            try:
                # Use a small timeout to allow the GUI thread to process other events
                item = self.output_queue.get(timeout=0.05)
                if isinstance(item, tuple) and item[0] == "DONE" and item[1] == f"STORE_{APP_STORE_PACKAGE_NAME}":
                    if item[2] != 0:
                        self.log_message(f"[ERROR] Failed to install/upgrade {APP_STORE_PACKAGE_NAME} (Return Code: {item[2]}). Aborting installation of {target_package}.\n")
                        # Signal thread completion explicitly here as we are returning early
                        self.output_queue.put(("FINISH_THREAD", None, None))
                        return # Stop installation process
                    else:
                        self.log_message(f"{APP_STORE_PACKAGE_NAME} installed/upgraded successfully.\n")
                        store_install_success = True
                        break # Continue with target app installation
                elif isinstance(item, str):
                     # Log regular messages from the command runner during the wait
                     self.log_message(item)
                elif isinstance(item, tuple) and item[0] == "FINISH_THREAD":
                     # If the runner signaled thread finish unexpectedly (e.g., FileNotFoundError), stop.
                     if not store_install_success: # Only stop if the store wasn't successfully installed
                        self.log_message(f"[ERROR] Runner thread finished unexpectedly during store installation. Aborting.\n")
                        return
                     # If store install was success, the FINISH_THREAD might be the one *we* put. Continue.

            except queue.Empty:
                 pass # Keep checking

            # Add a mechanism to stop if the main window is closed
            # if not self.winfo_exists(): return

        # Step 2: Install the selected application
        self.log_message(f"Installing {target_package}...\n")
        install_command = [sys.executable, '-m', 'pip', 'install', target_package]
        # Again, add --break-system-packages if needed for the target app
        # if sys.version_info >= (3, 11):
        #     install_command.append('--break-system-packages')

        self.command_runner.run_command(install_command, target_package)
        # The runner's finally block will put FINISH_THREAD after this command finishes


    def _start_uninstall_selected(self):
        """Initiates the uninstallation process in a separate thread."""
        display_name, package_name, _ = self._get_selected_app_info()
        if package_name:
            confirm = messagebox.askyesno("Confirm Uninstall", f"Are you sure you want to uninstall {display_name} ({package_name})?")
            if confirm:
                self.log_message(f"Attempting to uninstall: {display_name} ({package_name})\n")
                self.disable_buttons()

                # Create a thread to run the uninstallation command
                thread = threading.Thread(target=self._uninstall_app, args=(package_name,))
                thread.daemon = True
                thread.start()

    def _uninstall_app(self, package_name):
        """Uninstalls the specified application."""
        # Use -y to avoid interactive confirmation
        uninstall_command = [sys.executable, '-m', 'pip', 'uninstall', package_name, '-y']
        self.command_runner.run_command(uninstall_command, package_name)
        # The runner's finally block will put FINISH_THREAD


    def _start_run_selected(self):
        """Initiates running the application in a separate thread."""
        display_name, package_name, module_name = self._get_selected_app_info()
        if package_name:
            if not module_name:
                self.log_message(f"[ERROR] Cannot run {display_name}. No runnable module name ('module_name') specified in AVAILABLE_APPS config.\n")
                # Manually enable buttons since no thread was started
                self.enable_buttons()
                return

            self.log_message(f"Attempting to run: {display_name} (module: {module_name})\n")
            self.disable_buttons() # Disable while launching (process runs separately)

            # Create a thread to run the application command
            # Note: This thread will launch the target application as a subprocess.
            # If the target application is a GUI, it will open its own window(s).
            # The App Store GUI will remain open and responsive.
            thread = threading.Thread(target=self._run_app, args=(module_name, display_name))
            thread.daemon = True # Allow the main thread to exit even if this is running
            thread.start()


    def _run_app(self, module_name, display_name):
        """
        Runs the specified application module using `python -m <module_name>`.
        This launches the application in a separate process.
        If the launched application is a GUI, it will appear in its own window(s),
        separate from the App Store window.
        """
        # Use sys.executable to ensure we use the correct python interpreter
        run_command = [sys.executable, '-m', module_name]

        try:
            self.log_message(f"Launching process: {' '.join(run_command)}\n")
            # Use Popen and DO NOT wait for the process to finish.
            # This allows the launched app (especially GUIs) to run independently.
            # We don't typically capture stdout/stderr for GUI apps launched this way,
            # as they often detach or manage their own output/errors.
            # Setting creationflags can help detach the process from the console on Windows
            # subprocess.CREATE_NEW_CONSOLE or subprocess.DETACHED_PROCESS
            # Be cautious with creationflags as behavior varies by OS/environment.
            # A simple Popen is usually sufficient for GUI apps which handle their own windowing.

            process = subprocess.Popen(run_command) # No stdout/stderr pipes needed here for typical GUI launch
            self.log_message(f"{display_name} process launched with PID: {process.pid}\n")
            self.log_message(f"Interact with {display_name} in its own window(s).\n")

            # Signal that the *launching* process within this thread is done.
            # This allows the GUI to re-enable buttons. It does NOT mean the launched app has finished executing.
            self.output_queue.put(("FINISH_THREAD", None, None))

        except FileNotFoundError:
            self.output_queue.put(f"[ERROR] Python interpreter or module '{module_name}' not found.\n")
            self.output_queue.put(("FINISH_THREAD", None, None))
        except Exception as e:
            # Catch other potential errors during Popen, like permission issues
            self.output_queue.put(f"[ERROR] Failed to launch application '{display_name}': {e}\n")
            self.output_queue.put(("FINISH_THREAD", None, None))


    def _process_queue(self):
        """Checks the queue for messages and updates the GUI."""
        try:
            while True:
                # Use a small timeout to prevent blocking the GUI thread indefinitely
                item = self.output_queue.get_nowait()
                if isinstance(item, tuple):
                    if item[0] == "DONE":
                        package_name, rc = item[1], item[2]
                        status = "SUCCESS" if rc == 0 else "FAILED"
                        self.log_message(f"Operation on {package_name} {status} (Return Code: {rc}).\n\n")
                    elif item[0] == "FINISH_THREAD":
                         # This signal comes from the thread's finally block
                         self.enable_buttons()
                    # Add other tuple types here if needed (e.g., progress updates)
                elif isinstance(item, str):
                    self.log_message(item)
        except queue.Empty:
            pass # No items in the queue

        # Schedule the next check using self.after
        # Only reschedule if the window still exists
        if self.winfo_exists():
             self.after(100, self._process_queue)

    def on_closing(self):
        """Handle closing the window."""
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            # Signal runner threads to stop if they were written to check the event
            self.command_runner._stop_event.set()
            # If there's a lingering subprocess launched by command_runner (e.g. pip download),
            # you might want to terminate it here, but be cautious.
            # if self.command_runner._current_process and self.command_runner._current_process.poll() is None:
            #     try:
            #         self.command_runner._current_process.terminate()
            #     except OSError: # Process might have already exited
            #          pass
            self.destroy()


# --- Main Execution ---

if __name__ == "__main__":
    # Add a note if running directly without packaging
    print(f"Note: This app store is designed to be installed from PyPi (package '{APP_STORE_PACKAGE_NAME}').")
    print(f"When you click 'Install', it will attempt to install '{APP_STORE_PACKAGE_NAME}' from PyPi first.")
    print("The listed apps are placeholders. Replace them with actual PyPi package names and runnable module names.")
    print("-" * 20)

    # Check if running in a virtual environment (recommended)
    if not sys.prefix != sys.base_prefix:
        print("Warning: Not running in a virtual environment. Installation might affect your system Python.")
        print("It is highly recommended to run this app store from within a virtual environment.")
        print("-" * 20)
        # Optionally, ask the user if they want to continue or even exit.
        # if not messagebox.askyesno("Warning", "You are not running in a virtual environment.\nInstallation might affect your system Python.\nDo you want to continue?"):
        #     sys.exit(1)


    app = GeminiAppStore()
    # Handle window closing event
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()