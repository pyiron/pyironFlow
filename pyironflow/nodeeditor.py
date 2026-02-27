import ipywidgets as widgets
from pyironflow.treeview import TreeView
from pyironflow.nodeeditor_reactflow import NodeEditorWidget
from IPython.display import display
from pyiron_workflow import Workflow
import json

class GUILayout:
    screen_width = None
    screen_height = None
    flow_widget_width = None
    flow_widget_height = None
    output_widget_width = None


class NodeEditor:
    
    def __init__(
            self,
            wf_list=None, root_path=None,
            gui_layout: GUILayout | None = None,
            flow_widget_ratio: float = 0.95,
            reload_node_library: bool = False,
    ):
        """

        Args:
            ...
            gui_layout (GUILayout): ignored
            flow_widget_ratio (float): fraction of the widget width that is reserved for the workflow view.
            reload_node_library (bool): allow the refresh button to reload node modules
        """
        if gui_layout is not None:
            warnings.warn("gui_layout is ignored for the widget size, use flow_widget_ratio to control "
                          "'output_widget_width'")
        # throw a warning; debate value limits
        flow_widget_ratio = max(min(flow_widget_ratio, 0.9), 0.05)

        # generate empty default workflow if workflow list is empty
        if wf_list is None:
            wf_list = []
        if len(wf_list) == 0:
            wf_list = [Workflow('workflow')]

        if root_path is None:
            try:
                import pyiron_nodes
                root_path = pyiron_nodes.__spec__.submodule_search_locations[0]
            except (ImportError, IndexError):
                root_path = ""

        self._flow_widget_factor = 1 / (1/flow_widget_ratio - 1)
        self.workflows = wf_list


        self.out_log = widgets.Output(layout={'border': '1px solid black', 'overflow': 'auto', })
        self.out_widget = widgets.Output(layout={'border': '1px solid black', 'overflow': 'auto', })        
        self.wf_widgets = [NodeEditorWidget(
                wf=wf, root_path=root_path, log=self.out_log,
                out_widget=self.out_widget,
                reload_node_library=reload_node_library
            ) for wf in self.workflows]


        self.loop_name = widgets.Text(
            placeholder='Name of the Loop node',
            description='Name:',
            disabled=False   
        )

        self.loop_body = widgets.Text(
            placeholder='Name of the Loop body node',
            description='Body:',
            disabled=False   
        )

        self.loop_body2 = widgets.Text(
            placeholder='Name of the 2nd Loop body node',
            description='Body 2:',
            disabled=False   
        )

        self.loop_test = widgets.Text(
            placeholder='Name of the Loop test node',
            description='Test:',
            disabled=False   
        )
        
        self.loop_button = widgets.Button(
            description='Create Loop Node',
            disabled=False,
            button_style='', # 'success', 'info', 'warning', 'danger' or ''
            tooltip='Create',
            icon='check' # (FontAwesome names without the `fa-` prefix)
        )
        
        def on_button_clicked(b):
            self.wf_widgets[0].create_new_loop(
                self.accordion.children[3].children[1].value,
                self.accordion.children[3].children[2].value,
                self.accordion.children[3].children[3].value,
                self.accordion.children[3].children[0].value)
            self.wf_widgets[0].update_status()


        self.loop_button.on_click(on_button_clicked)  
        
        self.loop_dropdown = widgets.Dropdown(
            options=[('while'), ('for'), ('until')],
            #value=2,
            description='Loop type',
        )

        self.loop_box = widgets.VBox([self.loop_dropdown,self.loop_body, self.loop_body2, self.loop_test, self.loop_button])        
        self.view_flows = self.view_flows()
        self.tree_view = TreeView(root_path=root_path, flow_widget=self.wf_widgets[0], log=self.out_log)
        self.accordion = widgets.Accordion(children=[self.tree_view.gui,self.out_widget, self.out_log, self.loop_box],
                                           titles=['Node Library', 'Output', 'Logging Info', 'Loop'],
                                           layout={'border': '1px solid black',
                                                   'width': f'{int(100*(1-flow_widget_ratio))}%',
                                                   'flex': '1 0 auto',
                                                   'overflow': 'auto', })
        for widget in self.wf_widgets:
            widget.accordion_widget = self.accordion
            widget.tree_widget = self.tree_view

        self.gui = widgets.HBox([
            self.accordion,
            self.view_flows,
            # self.out_widget
        ],
            layout={
                'border': '1px solid black',
                'flex': '1 1 auto',
                'width': 'auto',
                'height': '75vh',
            })

    def get_workflow(self, tab_index=0):
        wf_widget = self.wf_widgets[tab_index]
        return wf_widget.get_workflow()

    def view_flows(self):
        tab = widgets.Tab(layout={'width': 'auto',
                                  'flex': f'{self._flow_widget_factor} 0 auto',
                                  'height': '100%'})
        tab.children = [self.display_workflow(index) for index, _ in enumerate(self.workflows)]
        tab.titles = [wf.label for wf in self.workflows]
        return tab

    def display_workflow(self, index: int):
        w = self.wf_widgets[index]
        return w.gui

    
