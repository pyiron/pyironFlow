import ipywidgets as widgets
from pyironflow.treeview import TreeView
from pyironflow.reactflow import PyironFlowWidget
from IPython.display import display
from pyiron_workflow import Workflow

__author__ = "Joerg Neugebauer"
__copyright__ = (
    "Copyright 2024, Max-Planck-Institut for Sustainable Materials GmbH - "
    "Computational Materials Design (CM) Department"
)
__version__ = "0.2"
__maintainer__ = ""
__email__ = ""
__status__ = "development"
__date__ = "Aug 1, 2024"

def get_screen_resolution():
    try:
        import tkinter as tk
    except ImportError:
        import Tkinter as tk
    try:
        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        return screen_width, screen_height
    except:
        screen_width = 1920
        screen_height = 930
        return screen_width, screen_height

class GUILayout:
    screen_width, screen_height = get_screen_resolution()
    flow_widget_width = screen_width / 1.6
    flow_widget_height = screen_height / 1.1625
    output_widget_width = 400


class PyironFlow:
    def __init__(self, wf_list=None, root_path='../pyiron_nodes/pyiron_nodes', gui_layout: GUILayout = GUILayout()):
        # generate empty default workflow if workflow list is empty
        if wf_list is None:
            wf_list = []
        if len(wf_list) == 0:
            wf_list = [Workflow('workflow')]

        self._gui_layout = gui_layout
        self.workflows = wf_list

        self.out_log = widgets.Output(layout={'border': '1px solid black',
                                              'width': f'{gui_layout.output_widget_width}px',
                                              'max_height': f'{self._gui_layout.flow_widget_height}px',
                                              'overflow': 'auto', })
        self.out_widget = widgets.Output(layout={'border': '1px solid black',
                                                 'max_width': f'{gui_layout.output_widget_width}px',
                                                 'overflow': 'auto', })
        self.wf_widgets = [PyironFlowWidget(wf=wf, root_path=root_path, log=self.out_log, out_widget=self.out_widget)
                           for wf in self.workflows]
        self.view_flows = self.view_flows()
        self.tree_view = TreeView(root_path=root_path, flow_widget=self.wf_widgets[0], log=self.out_log)
        self.accordion = widgets.Accordion(children=[self.tree_view.gui, self.out_widget, self.out_log],
                                           titles=['Node Library', 'Output', 'Logging Info'],
                                           layout={'border': '1px solid black',
                                                   'min_width': f'{gui_layout.output_widget_width}px',
                                                   'max_height': f'{self._gui_layout.flow_widget_height}px',
                                                   'overflow': 'auto', })
        for widget in self.wf_widgets:
            widget.accordion_widget = self.accordion

        self.gui = widgets.HBox([
            self.accordion,
            self.view_flows,
            # self.out_widget
        ],
            layout={'border': '1px solid black'})

    def get_workflow(self, tab_index=0):
        wf_widget = self.wf_widgets[tab_index]
        return wf_widget.get_workflow()

    def view_flows(self):
        tab = widgets.Tab()
        tab.children = [self.display_workflow(index) for index, _ in enumerate(self.workflows)]
        tab.titles = [wf.label for wf in self.workflows]
        return tab

    def display_workflow(self, index: int, out_flow=None):
        w = self.wf_widgets[index]

        if out_flow is None:
            out_flow = widgets.Output(layout={'border': '1px solid black',
                                              'width': f'{self._gui_layout.flow_widget_width}px',
                                              'max_height': f'{self._gui_layout.flow_widget_height+2}px'})

        with out_flow:
            display(w.gui)

        return out_flow
