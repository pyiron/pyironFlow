"""
code_editor module

This module provides a comprehensive code editing and execution environment.

The code_editor consists of three main components:

1. Toolbar:
   A set of control buttons for various operations:
   - Run: Executes the code in the editor
   - Save: Saves the current code to a file
   - Load: Loads code from a file into the editor
   - Refresh: Resets the editor and output window

2. Editor Window:
   A text area for writing and editing code, featuring:
   - Syntax highlighting for improved code readability
   - Line numbering
   - Auto-indentation

3. Output Window:
   Displays the results of code execution, including:
   - Standard output
   - Error messages
   - Execution status

This module is designed to provide a user-friendly interface for writing,
editing, and running code, making it suitable for educational purposes,
quick prototyping, or as part of a larger integrated development environment.

Usage:
    # The following line is critical to activate panel (without the code 
    # editor will not be displayed). After running these two lines reset 
    # Kernel and run again! 

    import panel
    panel.extension()

    import pyironflow.code_editor
    editor = code_editor.CodeEditor()
    editor.show()

Note: Ensure all necessary dependencies are installed before using this module.
"""

import panel
import ipywidgets as widgets
from IPython.display import display

panel.extension()


class CodeEditorView:
    def __init__(self, code: str, width: int = 400):
        self.code = code
        self._width = width
        self.setup_buttons()
        self.setup_editor_widget()
        self.setup_output_widget()
        self.setup_toolbar()

    def setup_editor_widget(self):
        self.panel_editor = panel.widgets.CodeEditor(
            value=self.code,
            language="python",
            theme="monokai",
            min_height=100,
            max_width=self._width,
            sizing_mode="stretch_width",
        )
        self.code_editor = panel.ipywidget(self.panel_editor)

    def setup_buttons(self):
        button_layout = widgets.Layout(width="100px")  # Define the width of the buttons

        self.run_button = widgets.Button(
            description="Run", button_style="success", icon="play", layout=button_layout
        )
        self.save_button = widgets.Button(
            description="Save", button_style="info", icon="save", layout=button_layout
        )
        self.load_button = widgets.Button(
            description="Load",
            button_style="warning",
            icon="folder-open",
            layout=button_layout,
        )
        self.refresh_button = widgets.Button(
            description="Refresh",
            button_style="danger",
            icon="refresh",
            layout=button_layout,
        )

        self.run_button.on_click(self.on_run_button_clicked)
        self.save_button.on_click(self.on_save_button_clicked)
        self.load_button.on_click(self.on_load_button_clicked)
        self.refresh_button.on_click(self.on_refresh_button_clicked)

    def setup_output_widget(self):
        self.output = widgets.Output(
            layout=widgets.Layout(
                width=f"{self._width}px",
                border="1px solid black",
                min_height="100px",
                max_height="200px",
                left="6pt",
                overflow="auto",
            )
        )

    def on_run_button_clicked(self, b):
        with self.output:
            self.output.clear_output()
            print("run button")
            code = self.panel_editor.value
            try:
                local_scope = {}
                exec(code, {}, local_scope)  # Using 'exec' to execute code
                display(local_scope['wf'].run())
            except Exception as e:
                print(f"An error occurred: {e}")

    def on_save_button_clicked(self, b):
        with self.output:
            self.output.clear_output()
            # Add your save functionality here...
            print("Save button clicked")

    def on_load_button_clicked(self, b):
        with self.output:
            self.output.clear_output()
            # Add your load functionality here...
            print("Load button clicked")

    def on_refresh_button_clicked(self, b):
        with self.output:
            self.output.clear_output()
            # Add your refresh functionality here...
            print("Refresh button clicked")

    def setup_toolbar(self):
        toolbar_layout = widgets.Layout(
            width=f"{self._width}px",
            border="1px solid black",
            left="6pt",
        )
        self.toolbar = widgets.HBox(
            [self.run_button, self.save_button, self.load_button, self.refresh_button],
            layout=toolbar_layout,
        )

    def show(self):
        editor_widget = widgets.VBox(
            [self.toolbar, self.code_editor, self.output],
            layout=widgets.Layout(align_items="stretch"),
        )
        return display(editor_widget)
