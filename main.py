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
APP_STORE_PACKAGE_NAME = "gemini_ai_app_store" # Replace with your actual PyPi package name!
# Define the apps available in the store
# Format: {"Display Name": {"package_name": "pypi-package-name", "module_name": "module_to_run_with_python_m"}}
AVAILABLE_APPS = {
    "Gemini Chat App": {"package_name": "gemini_chat_app", "module_name": "gemini_chat_app"}
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

    def run_command(self, command, package_name):
        """Runs a command in a subprocess and puts output/result in the queue."""
        try:
            self.output_queue.put(f"--> Running command: {' '.join(command)}\n")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            # Read stdout and stderr in real-time
            while True:
                output = process.stdout.readline()
                error = process.stderr.readline()
                if output == '' and error == '' and process.poll() is not None:
                    break
                if output:
                    self.output_queue.put(output)
                if error:
                    self.output_queue.put(f"[ERROR] {error}") # Differentiate errors
                # Small sleep to prevent tight loop
                if not output and not error:
                     threading.sleep(0.01)

            rc = process.wait() # Wait for the process to finish
            self.output_queue.put(f"<-- Command finished with return code: {rc}\n")
            self.output_queue.put(("DONE", package_name, rc)) # Signal command completion

        except FileNotFoundError:
            self.output_queue.put(f"[ERROR] Command not found. Make sure Python and pip are in your PATH.\n")
            self.output_queue.put(("DONE", package_name, 1)) # Signal failure
        except Exception as e:
            self.output_queue.put(f"[ERROR] An unexpected error occurred: {e}\n")
            self.output_queue.put(("DONE", package_name, 1)) # Signal failure
        finally:
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
        list_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        self.app_listbox = tk.Listbox(list_frame, width=50, height=10)
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

        self.output_text = tk.Text(output_frame, height=8, state=tk.DISABLED)
        self.output_text.pack(fill=tk.BOTH, expand=True)

    def _populate_app_list(self):
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
        self.install_button.config(state=tk.DISABLED)
        self.uninstall_button.config(state=tk.DISABLED)
        self.run_button.config(state=tk.DISABLED)

    def enable_buttons(self):
        selected_indices = self.app_listbox.curselection()
        if selected_indices:
            self.install_button.config(state=tk.NORMAL)
            self.uninstall_button.config(state=tk.NORMAL)
            self.run_button.config(state=tk.NORMAL)

    def log_message(self, message):
        """Appends a message to the output text area."""
        self.output_text.config(state=tk.NORMAL)
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
            return display_name, app_info["package_name"], app_info.get("module_name") # module_name might be optional
        else:
            self.log_message(f"Error: Could not find info for selected app: {display_name}\n")
            return None, None, None

    def _start_install_selected(self):
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
        # Step 1: Ensure the app store is installed from PyPi
        self.log_message(f"Ensuring {APP_STORE_PACKAGE_NAME} is installed from PyPi...\n")
        store_install_command = [sys.executable, '-m', 'pip', 'install', '--upgrade', APP_STORE_PACKAGE_NAME]
        self.command_runner.run_command(store_install_command, APP_STORE_PACKAGE_NAME)

        # Wait for the store install command to finish in the queue
        # This is a bit simplistic; a proper thread management would be better
        # But for simple sequential commands, waiting for the signal in the queue works
        while True:
            try:
                item = self.output_queue.get(timeout=0.1)
                if isinstance(item, tuple) and item[0] == "DONE" and item[1] == APP_STORE_PACKAGE_NAME:
                    if item[2] != 0:
                        self.log_message(f"[ERROR] Failed to install/upgrade {APP_STORE_PACKAGE_NAME}. Aborting installation of {target_package}.\n")
                        self.output_queue.put(("FINISH_THREAD", None, None)) # Signal thread completion
                        return # Stop installation process
                    else:
                        self.log_message(f"{APP_STORE_PACKAGE_NAME} installed/upgraded successfully.\n")
                        break # Continue with target app installation
                elif isinstance(item, str):
                     self.log_message(item) # Log messages from the command
            except queue.Empty:
                 pass # Keep checking
            if self._stop_event.is_set(): # Check if we should stop
                 self.output_queue.put(("FINISH_THREAD", None, None))
                 return


        # Step 2: Install the selected application
        self.log_message(f"Installing {target_package}...\n")
        install_command = [sys.executable, '-m', 'pip', 'install', target_package]
        self.command_runner.run_command(install_command, target_package)


    def _start_uninstall_selected(self):
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


    def _start_run_selected(self):
        display_name, package_name, module_name = self._get_selected_app_info()
        if package_name:
            if not module_name:
                self.log_message(f"[ERROR] Cannot run {display_name}. No module name specified.\n")
                return

            self.log_message(f"Attempting to run: {display_name} ({module_name})\n")
            self.disable_buttons() # Disable while launching (process runs separately)

            # Create a thread to run the application command
            # Note: This runs the app in a subprocess. Its output may appear in the
            # console where this app store was launched. Its GUI will open separately.
            thread = threading.Thread(target=self._run_app, args=(module_name,))
            thread.daemon = True
            thread.start()


    def _run_app(self, module_name):
        """Runs the specified application module."""
        # Use sys.executable to ensure we use the correct python interpreter
        run_command = [sys.executable, '-m', module_name]
        # We don't capture output here typically, as the app is expected to run
        # as a separate interactive process (CLI) or open its own GUI.
        # Use Popen without waiting if we don't want the GUI to freeze.
        try:
            self.log_message(f"Launching process: {' '.join(run_command)}\n")
            # Use Popen and don't wait
            process = subprocess.Popen(run_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            # Log the PID (optional)
            self.log_message(f"App process started with PID: {process.pid}\n")

            # Note: Output from the launched app's stdout/stderr won't appear
            # here unless we actively read from process.stdout/stderr in a loop,
            # which is complex for long-running apps and can still block if pipes fill up.
            # For simplicity, we just launch and re-enable buttons. The user interacts
            # with the launched app directly (either in the console or its own window).

            self.log_message(f"Process launched. Interact with {module_name} separately.\n")
            # Signal that the launching process is done (not the app's execution)
            self.output_queue.put(("FINISH_THREAD", None, None))

        except FileNotFoundError:
            self.output_queue.put(f"[ERROR] Python interpreter or module '{module_name}' not found.\n")
            self.output_queue.put(("FINISH_THREAD", None, None))
        except Exception as e:
            self.output_queue.put(f"[ERROR] Failed to launch application: {e}\n")
            self.output_queue.put(("FINISH_THREAD", None, None))


    def _process_queue(self):
        """Checks the queue for messages and updates the GUI."""
        try:
            while True:
                item = self.output_queue.get_nowait()
                if isinstance(item, tuple):
                    if item[0] == "DONE":
                        package_name, rc = item[1], item[2]
                        status = "SUCCESS" if rc == 0 else "FAILED"
                        self.log_message(f"Operation on {package_name} {status} (Return Code: {rc}).\n\n")
                    elif item[0] == "FINISH_THREAD":
                         self.enable_buttons()
                elif isinstance(item, str):
                    self.log_message(item)
        except queue.Empty:
            pass # No items in the queue

        # Schedule the next check
        self.after(100, self._process_queue)

    def on_closing(self):
        """Handle closing the window."""
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self._stop_event.set() # Signal any running threads to stop (if they check)
            self.destroy()

# --- Main Execution ---

if __name__ == "__main__":
    # Add a note if running directly without packaging
    print(f"Note: This app store is designed to be installed from PyPi (package '{APP_STORE_PACKAGE_NAME}').")
    print(f"When you click 'Install', it will attempt to install '{APP_STORE_PACKAGE_NAME}' from PyPi first.")
    print("The listed apps are placeholders. Replace them with actual PyPi package names.")
    print("-" * 20)

    app = GeminiAppStore()
    app.protocol("WM_DELETE_WINDOW", app.on_closing) # Handle window closing
    app.mainloop()
