#========================================================================================#
#                                       IDLEARN                                          #
#                                        gui.py                                          #
#========================================================================================#

# Filename: gui.py
# Author: diomir0
# Date of creation: 05 Jul 2025

# This script defines the GUI class running the graphical interface of the Idlearn app. 

import threading
import customtkinter as ctk
import tkinter
from .pipeline import Pipeline
from .utils import get_toc


ctk.set_appearance_mode("dark")  # Options: "System" (default), "Dark", "Light"
#ctk.set_default_color_theme("blue")  # Other options: "dark-blue", "green", etc.


class ToplevelWindow(ctk.CTkToplevel):
        
    def __init__(self, master=None, text="Information Dialog"):
        super().__init__(master)
        self.geometry("400x100")
        self.title = "Warning"
        self.text = text
        self.label = ctk.CTkLabel(self, text=self.text)
        self.label.pack(padx=20, pady=20)
        self.button_ok = ctk.CTkButton(self, text="OK", command=self.destroy())


class MetadataFrame(ctk.CTkScrollableFrame):
    
    def __init__(self, master, title):
        super().__init__(master)

        self.grid_columnconfigure((0, 1), weight=1)

        self.title = title
        self.title = ctk.CTkLabel(self, text=self.title, fg_color="gray30", corner_radius=6)
        self.title.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="ew", columnspan=2)
        self.sections = []
        self.toc_section = []

        # Create labels for PDF metadata visualization
        self.title_label = ctk.CTkLabel(self, text="Title: ", fg_color="transparent", anchor='w', justify="left")
        self.title_label.grid(row=1, column=0, padx=20, pady=10, sticky='ew')
        self.title_info = ctk.CTkLabel(self, text="", fg_color="transparent", anchor='w', justify="left", wraplength=300)
        self.title_info.grid(row=1, column=1, padx=20, pady=10, sticky='ew')
        self.author_label = ctk.CTkLabel(self, text="Author: ", fg_color="transparent", anchor='w', justify="left")
        self.author_label.grid(row=2, column=0, padx=20, pady=10, sticky='ew')
        self.author_info = ctk.CTkLabel(self, text="", fg_color="transparent", anchor='w', justify="left", wraplength=300)
        self.author_info.grid(row=2, column=1, padx=20, pady=10, sticky='ew')
        self.toc_label = ctk.CTkLabel(self, text="ToC: ", fg_color="transparent", anchor='w', justify="left")
        self.toc_label.grid(row=5, column=0, padx=20, pady=(10, 0), sticky='ew')

    
    def update_label_text(self, label, info):
        text = label.cget("text")
        label.configure(text=info)

    
    def update_metadata(self, doc):
        metadata = doc.metadata
        self.update_label_text(self.title_info, metadata['title'])
        self.update_label_text(self.author_info, metadata['author'])
        self.create_toc_selection(doc)


    def create_toc_selection(self, doc):
        for i, sec in enumerate(get_toc(doc)):
            idx = sec[0]
            sec_title = sec[1]
            page_idx = sec[2]
            checkvar = ctk.StringVar(value = 'off')
            self.checkbox = ctk.CTkCheckBox(self, text=sec_title, command=self.add_section(sec),
                                            variable=checkvar, onvalue="on", offvalue="off", hover = True, 
                                            checkbox_width=16, checkbox_height=16)
            self.checkbox.grid(row=5+i, column=1, padx=20+40*(idx-1), pady=(0,0), sticky='w')
            self.checkbox._text_label.configure(wraplength=300, justify="left")
            self.toc_section.append(self.checkbox)
            self.label = ctk.CTkLabel(self, text=page_idx, fg_color="transparent", anchor='e', justify="right")
            self.label.grid(row=5+i, column=2, padx=20, pady=(0, 0), sticky='e')


    def add_section(self, section):
        if section not in self.sections:
            self.sections.append(section)
        else:
            self.sections.remove(section)


class IdlearnApp(ctk.CTk):
        
    def __init__(self):
        super().__init__()

        self.pipeline = None

        self.filename = None 
        self.outfolder = None
        self.cards = ctk.StringVar(value="off")

        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure((0, 1, 2), weight=1)
        
        # Define basic info
        self.title("IDLEARN")
        self.geometry("1024x400")

        # Create input file textbox
        self.textbox_input = ctk.CTkTextbox(self, width = 300, height = 30)
        self.textbox_input.grid(row=0, column=0, padx=10, pady=20)
        self.textbox_input.insert("0.0", "No file selected")
        #self.textbox_input.configure(state="disabled")  # configure textbox to be read-only
        
        # Create input file button
        self.button_filename = ctk.CTkButton(self, text="Choose file", command=self.make_openfile, corner_radius=24, hover =True)
        self.button_filename.grid(row=0, column=1, padx=10, pady=20, sticky='ew')
        
        # Create output folder textbox
        self.textbox_output = ctk.CTkTextbox(self, width = 300, height = 30)
        self.textbox_output.grid(row=1, column=0, padx=10, pady=20)
        self.textbox_output.insert("0.0", "No folder selected")
        #self.textbox_output.configure(state="disabled")  # configure textbox to be read-only
        
        # Create output file button
        self.button_outfolder = ctk.CTkButton(self, text="Choose destination folder", command=self.make_outfolder, corner_radius=24, hover =True)
        self.button_outfolder.grid(row=1, column=1, padx=10, pady=20, sticky='ew')
        
        # Create run button
        self.button_run = ctk.CTkButton(self, text="Run", command=self.make_run, corner_radius=24, hover =True)
        self.button_run.grid(row=2, column=1, padx=20, pady=20)
        
        # Create checkbox to either generate Anki cards or nor
        self.checkbox = ctk.CTkCheckBox(self, text="Anki cards", command=None, hover=True,
                                        variable=self.cards, onvalue="on", offvalue="off")
        self.checkbox.grid(row=2, column=0, padx=20, pady=(0,0))
        
        # Create metadata frame
        self.metadata_frame = MetadataFrame(self, title="File Metadata")
        self.metadata_frame.grid(row=0, column=2, padx=10, pady=(10, 10), sticky='ewns', rowspan=3)
        
        # Define top-level window
        self.toplevel_window = None

    
    def make_openfile(self):
        self.filename = tkinter.filedialog.askopenfilename()
        self.textbox_input.delete("0.0", "end")
        self.textbox_input.insert("0.0", self.filename)
        self.pipeline = Pipeline(self.filename, self.outfolder, self.check_cards())
        if len(self.metadata_frame.toc_section) != 0:
            for checkbox in self.metadata_frame.toc_section:
                checkbox.destroy()
            self.metadata_frame.toc_section = []
        self.metadata_frame.update_metadata(self.pipeline.doc)
                               
    
    def make_outfolder(self):
        self.outfolder = tkinter.filedialog.askdirectory()
        self.textbox_output.delete("0.0", "end")
        self.textbox_output.insert("0.0", self.outfolder)

    
    def make_run(self):
        if self.filename is not None:
            if self.outfolder is not None:
                self.pipeline.run(self.metadata_frame.sections)
            else:
                self.open_toplevel(text="Select output folder")
        else:
            self.open_toplevel(text="Select input file")

    
    def check_cards(self):
        if self.cards.get() == "on" :
            return True
        else:
            return False

    
    def open_toplevel(self, text):
        if self.toplevel_window is None or self.toplevel_window.winfo_exists():
            self.toplevel_window = ToplevelWindow(self, text)
        else:
            self.toplevel_window.focus()
