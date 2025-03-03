import sys
import os
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit

class FolderSelectionDialog(QDialog):
    def __init__(self, directory):
        super().__init__()

        self.selected_folder = None  # Store the selected folder
        self.setWindowTitle("Select a Folder")
        self.setMinimumWidth(300)

        # Get list of folders in the directory
        self.folders = [f for f in os.listdir(directory) if os.path.isdir(os.path.join(directory, f))]

        # Create GUI elements
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Select a folder:"))

        self.combo_box = QComboBox()
        self.combo_box.addItems(self.folders)
        layout.addWidget(self.combo_box)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept_selection)
        layout.addWidget(ok_button)

        self.setLayout(layout)

    def accept_selection(self):
        """ Store the selected folder and close the dialog. """
        self.selected_folder = self.combo_box.currentText()
        self.accept()  # Closes the dialog

class NameEntryDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.entered_name = None  # Store the user input
        self.setWindowTitle("Enter a Name")
        self.setMinimumWidth(300)

        # Create GUI elements
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Enter a name:"))

        self.line_edit = QLineEdit()
        layout.addWidget(self.line_edit)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept_input)
        layout.addWidget(ok_button)

        self.setLayout(layout)

    def accept_input(self):
        """ Store the entered name and close the dialog. """
        self.entered_name = self.line_edit.text()
        self.accept()  # Closes the dialog

def select_folder(directory):
    """ Open the folder selection dialog and return the selected folder. """
    dialog = FolderSelectionDialog(directory)
    result = dialog.exec_()
    return dialog.selected_folder if result == QDialog.Accepted else None

def enter_name():
    """ Open the name entry dialog and return the entered name. """
    dialog = NameEntryDialog()
    result = dialog.exec_()
    return dialog.entered_name if result == QDialog.Accepted else None

if __name__ == "__main__":
    app = QApplication(sys.argv)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    selected_folder = select_folder(script_dir)

    if selected_folder:
        print(f"Selected folder: {selected_folder}")
        entered_name = enter_name()
        
        if entered_name:
            print(f"Entered name: {entered_name}")
        else:
            print("No name entered.")
    else:
        print("No folder selected.")

    sys.exit(app.exec_())  # Ensures the application exits cleanly
