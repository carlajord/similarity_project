import json
from pathlib import Path
from dotenv import load_dotenv
import numpy as np, pandas as pd
from tempfile import TemporaryDirectory
from uuid import uuid4

from PIL import Image
from pdf2image import convert_from_path
import pytesseract
import faiss

from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from langchain_core.messages import SystemMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate
from langchain_core.documents import Document

from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore


load_dotenv()

AZURE_DEPLOYMENT = "gpt-4o"
API_VERSION = "2024-08-01-preview"

TEMP_STANDARD = 15.0 # degF
PRES_STANDARD = 14.7 # psia

HIGH_TEMP_THRESHOLD = 212.0 # degF
HIGH_PRES_THRESHOLD = 2000.0 # psia

DATA_PATH = Path(__file__).parent.joinpath("data")
#DATA_PATH = os.path.join(os.path.abspath(""), ".." ,"data")

class PVTAnalyser:

    def __init__(self, pdf_files) -> None:

        uuids = [str(uuid4()) for _ in range(len(pdf_files))]

        output_files = []
        for file_name in pdf_files:
            output_files.append(file_name.with_suffix('.txt'))

        self.data = pd.DataFrame()
        self.data['id'] = uuids
        self.data['raw_pdf'] = pdf_files
        self.data['raw_txt'] = output_files

        self.llm = AzureChatOpenAI(
            azure_deployment=AZURE_DEPLOYMENT,  # or your deployment
            api_version=API_VERSION,  # or your api version
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            # handle_parsing_errors=True,
        )

        self.embeddings = AzureOpenAIEmbeddings()

    def initialize_vector_store(self):
        index = faiss.IndexFlatL2(len(self.embeddings.embed_query("hello world")))

        vector_store = FAISS(
            embedding_function=self.embeddings,
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )

        return vector_store

    def convert_pdf_to_text(self):

        for file, outfile in zip(self.data['raw_pdf'], self.data['raw_txt']):
            image_file_list = []
            with TemporaryDirectory() as tempdir:
                pdf_pages = convert_from_path(file, 500)
            for page_enumeration, page in enumerate(pdf_pages, start=1):
                filename = f"{tempdir}\page_{page_enumeration:03}.jpg"
                page.save(filename, "JPEG")
                image_file_list.append(filename)
            with open(outfile, "a") as output_file:
                for image_file in image_file_list:
                    text = str(((pytesseract.image_to_string(Image.open(image_file)))))
                    text = text.replace("-\n", "")
                    output_file.write(text)

    def extract_data(self):

        chain = self.get_chain_to_extract_data()
        self.data = self.data.apply(lambda row: self.extract_data_per_file(chain, row), axis=1)

    def extract_data_per_file(self, chain, row):

        outfile = row['raw_txt']

        with open(outfile, encoding='utf-8') as file:
            text = file.read()
        response = chain.invoke({"Input": text})
        file_response = json.loads(response.content)

        row['extracted_conditions'] = file_response['Conditions'][0]
        row['extracted_components'] = file_response['Components'][0]

        return row

    def get_chain_to_extract_data(self):
        system_msg = extract_data_instructions()
        chat_template = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=(system_msg)),
                HumanMessagePromptTemplate.from_template("{Input}"),
            ]
        )
        chain = chat_template | self.llm
        return chain

    def process_extracted_data(self):
        # use semantic similarity to get compositions in Symmetry format
        self.data = self.data.apply(lambda row: self.process_components_per_file(row), axis=1)
        self.data = self.data.apply(lambda row: self.process_conditions_per_file(row), axis=1)
    
    def process_components_per_file(self, row):

        # start a clean vector store
        vector_store = self.initialize_vector_store()

        components_sym = symmetry_components()
        components_raw = row['extracted_components']

        # add raw components to the vector store
        raw_components = []
        for comp in list(components_raw.keys()):
            raw_components.append(Document(page_content=comp))
        vector_store.add_documents(documents=raw_components)

        # use vector store similarity search to find equivalent for Symmetry components
        sym_component = {}
        for comp_sym in components_sym:
            resp = vector_store.similarity_search_with_relevance_scores(comp_sym, k=1)
            pdf_component = resp[0][0].page_content
            try:
                var_val = np.float32(components_raw[pdf_component])
            except:
                var_val = 0.0
            sym_component[comp_sym] = var_val
        
        # compute pseudo-component
        val_sum = np.sum(np.fromiter(sym_component.values(), dtype=float))
        c6_plus = 100.-val_sum
        sym_component['C6+'] = c6_plus
        if c6_plus < 0.: sym_component['C6+'] = 0.
        
        # normalize final composition
        normalized_values = np.fromiter(sym_component.values(), dtype=float)/np.sum(np.fromiter(sym_component.values(), dtype=float))
        sym_component_normalized = dict(zip(sym_component, normalized_values))

        row['components'] = sym_component_normalized

        return row

    def process_conditions_per_file(self, row):
        
        conditions_raw = row['extracted_conditions']
        temp_val = conditions_raw['Sample Temperature']
        pres_val = conditions_raw['Sample Pressure']

        try:
            temp_val = np.float64(temp_val)
            if (temp_val < TEMP_STANDARD) or (temp_val > HIGH_TEMP_THRESHOLD):
                temp_val = TEMP_STANDARD
        except:
            temp_val = TEMP_STANDARD

        try:
            pres_val = np.float64(pres_val)
            if (pres_val < PRES_STANDARD) or (pres_val > HIGH_PRES_THRESHOLD):
                pres_val = PRES_STANDARD
        except:
            pres_val = PRES_STANDARD

        row['temperature'] = temp_val
        row['pressure'] = pres_val

        return row

    def sym_thermo_set_script(self):
        self.data = self.data.apply(lambda row: self.make_sym_thermo_script_per_file(row), axis=1)

    def make_sym_thermo_script_per_file(self, row):
        components = row['components']
        temperature = row['temperature']
        pressure = row['pressure']
        
        components_cmd = []
        compositions = ""
        for comp_name in symmetry_components():
            components_cmd.append(f'$VMGThermo + {comp_name}')
            compositions = compositions + f'{components[comp_name]} '

        if 'C6+' in components.keys():
            compositions = compositions + f'{components["C6+"]} '
            components_cmd.append('''$VMGThermo.C6+* = HypoCompound """
MolecularWeight = 98
LiquidDensity@298 = 611.9
"""''')
        conditions_cmd =[ f"'/S1.In.T' = {temperature} F", f"'/S1.In.P' = {pressure} psia"]

        # add water, ethylene glycol and methanol to the list
        compositions = compositions + '0 0 0'

        set_thermo_cmds = components_cmd + [
            '$VMGThermo + WATER',
            '$VMGThermo + ETHYLENE_GLYCOL',
           ' $VMGThermo + METHANOL',
            "/S1 = Stream.Stream_Material()" ] + \
            conditions_cmd + \
            ["'/S1.In.MoleFlow' = 1",
            f"'/S1.In.Fraction' = {compositions}"
        ]

        return row

def extract_data_instructions():
    system_msg = """
You are a chemical engineer looking at PVT reports.
You extract sampling conditions information from the report, such as Sample Pressure and Sample Temperature.
You extract component and composition from the report, such as Methane 90% mole, Ethane 10% mole, etc.
You convert the information extracted into a JSON format under the keys "Conditions" and "Components".
Output the information strictly in the JSON format without any extra characters or markdown (such as json or backticks).

- For the Conditions key:
Each entry within the "Conditions" array should be a dictionary representing the Sample Pressure or Sample Temperature.
The Sample Pressure and Sample Temperature must be reported along with their respective units.
If the value is unavailable, put N/A.

- For the "Components key:
Each entry within the "Components" array should be a dictionary representing a single component and its corresponding Mole% value from the document.
Format it such that each dictionary has a key as the component name and value as the "Mole%".
If the component "%" is not available put N/A.
Make sure to include the word "Plus" or the character "+" in the component name when it is present.

- Example of input and expected output:

Input:
PROJECT NO. COMI'ANY NAME ACCGUNT NO. - PRODUCER LEASE NO.  NAME. DESCRIP ***FIELD DATA®** SAMPI ED BY: SAMPLE PRFS. : COMMENTS      COMPONENT HELIU! HYDROGEN OXYGEN/ARGON NITROGEN  o2  METHANE ETHANE PROPANE I-BUTANE N-BUT/NE I-PENTANE PEN"ANT: HEXANES PLUS TOTALS               BTEX COMPONENTS MOLE%  BENZE        TOTAL BTEX  (CALC: GASTD 214594 & TF- “DHA (DETAILED HYDROCARBON AN:  ASTH DCI0 THIS DAT:      EMPACT ANALYTICAL SYSTEMS, INC  365  SOUTH MAIN STREET  BRIGHTON, CO 80601  EXTENDED  (303) 637-0150  NATURAL GAS ANALYSIS (*DHA)                 0312028 ANALYSISNO.: 03 COMPLIANCE PARTNERS ANALYSIS DATE:  DECEMBER 7, 2003 SAMPLEDATE :  DECEMBER 4, 2003 WESTERN GAS TO: CYLINDERNO.: 0299 MDU #6 P SCHLAGEL AMBIENT TEMP.: 800 SAMPLE TEMP. 80 GRAVITY NO PROBE GPM@ GPM@ MOLE % MASS % 14.696 14.73 0.004 G001 — = 0.000 0.000 - - 0.000 0.000 - - o7 0184 = = 227 5619 - - 971 83.565 - - 2852 4805 0.7610 07628 0.910 2248 0.2502 02508 019 0637 0.0640 00641 0228 0.741 00717 00719 0.093 0375 0.0339 0.0340 6.065 0.261 00235 0.0236 0285 1564 01187 0.1187 100.000 100.000 13230 13259 WT% BTU@ 14.696 1473 0.008 0.038 NET DRY REAL: 947.15 sef 949.34 fsef 0.001 0.008 LOW NET WET RFAL: 93064 Jscf 932.83 fsef 0011 0058 GROSS DRY REAL 1049.5 fscf 1052.02 fsef 0.005 0032 HIGH ~ GROSS WET REAL 1031.30 /sef 1033.73 fsef 0026 0136 NET DRY REAL: 20142 My GROSS DRY REAL : 22321 b DENSITY (ATR=1) 06172 169 & 605 COMPRESSIBILITY FACTOR 099776        BEEN ACQUIRED THROUGH APPLICATION OF CURRENT STATE-OF - THE-ART ANALYTICAL TECHNIQUES  THE USE (.F T7IIS INFORMATION IS THE RESPONSIBLITY OF THE USER. EMPACT ANALYTICAL SYSTEMS, ASSUMES NO  RESPON:     7Y FOR ACCURACY OF THE REFORTED INFORMATION NOR ANY CONSEQUENCES OF IT'S APPLICATION  59-013 -0/23  SW NW Frement (wnf)/  Madilen Feld . UniotFm,  | -3%-90   EMPACT ANALYTICAL SYSTEMS, INC 365 SOUTH MAIN STREET  BRIGHTON, CO 80601 303) 637-0150  E & P /GlyCalc Information        PROJECTNO. 0312028 ANALYSISNO.: 03 COMPANY NAME:  COMPLIANCE PARTNERS ANALYSIS DATE:  DECEMBER 7, 2003 ACCOUNTNO. : SAMPLE DATE DECEMBER 4, 2003 PRODUCER WESTERN GAS TO:  LEASE NO. CYLINDER NO. 0299 NAMEDESCRIP:  MDU #6  *+++FIELD DATA***  SAMPLED BY: P SCHLAGEL AMBIENT TEMP. SAMPLE PRES. 800 GRAVITY  : COMMENTS NO PROBE SAMPLE TEMP 50 Comporenet Mole % Wi %  Helium 0.004 0.001 Hydrogen 0.000 0.000 Methano 0.000 0.000 Carbon Nioxide 2279 5610 Nitrager 0117 0.184 Methane 92,971 83.565 Ethane 2.852 4.805 Propane 0910 2248 Isobutan: 0.19 06.637 n-Butane 0.228 0.741 Isopenanc 0.093 0375 n-Pentanc 0.065 0.261 Cyclopen-ane 0.006 0023 n-Hexane 0.026 0123 Cyclohexane 0.021 0.100 Other Heanes 0.066 0314 Heptanes 0.045 0258 Methycyclohexane 0037 0.205 2,24 Trimethylpentane 6.000 0.000 Benzene 0.009 0038 Toluene 001 0.058 Fihylbenzene 0.001 0.008 Xylenes 0005 0.032 C8+ Heavies 0.05% 0.405 Subtotal 106,000 100.000 Oxygen 0.000 0.000  Total 100.000 100.000

Output:
{  "Conditions": [{"Sample Pressure": "800 psia", "Sample Temperature": "80 degF"}],  "Components": [     {"Helium": "0.004", "Hydrogen": "0.000", "Oxygen/Argon": "0.000", "Nitrogen": "0.117", "CO2": "2.279", "Methane": "92.971", "Ethane": "2.852", "Propane": "0.910", "i-Butane": "0.196", "n-Butane": "0.228", "i-Pentane": "0.093", "n-Pentane": "0.065", "Hexanes Plus": "0.285"}   ] }
"""
    return system_msg

def symmetry_components():
    return ["METHANE", "ETHANE", "PROPANE", "ISOBUTANE", "n-BUTANE", \
        "ISOPENTANE", "n-PENTANE", "NITROGEN", "CARBON_DIOXIDE"]



def run():
    
    pdf_files = [
        DATA_PATH.joinpath("G929147A_LP_Sales.pdf"),
        DATA_PATH.joinpath("G1320123A_wellhead.pdf"),
        DATA_PATH.joinpath("G1321243A_wellhead.pdf")
    ]

    p = PVTAnalyser(pdf_files)
    p.convert_pdf_to_text()
    p.extract_data()
    p.process_extracted_data()
    p.sym_thermo_set_script()
    p.data.to_csv(DATA_PATH.joinpath("processed_files.csv"))

    return 

if __name__ == '__main__':
    run()