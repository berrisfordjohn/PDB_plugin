# Plugin for PyMol to display the images show on PDBe's website
# Author: John Berrisford
# Date: June 2018
#
# parsing the input
import json
import datetime
import socket
import re, os
import time
import sys
import random
import logging

import pymol
from pymol import cmd
from pymol import stored
from chempy.cif import *

# logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# API calls
server_root = "https://www.ebi.ac.uk/pdbe/api/"
summaryURL = server_root + "pdb/entry/summary/"
poly_seq_schemeURL = server_root + "pdb/entry/residue_listing/"
protein_mappingURL = server_root + "mappings/"
nucleic_mappingURL = server_root + "nucleic_mappings/"
# seqURL = server_root + "mappings/sequence_domains/entry/"
moleculesURL = server_root + "pdb/entry/molecules/"
validationURL = server_root + 'validation/global-percentiles/entry/'
validation_residueURL = server_root + 'validation/protein-RNA-DNA-geometry-outlier-residues/entry/'
validation_ramaURL = server_root + 'validation/protein-ramachandran-sidechain-outliers/entry/'

# ftp site
ebi_ftp = 'ftp://ftp.ebi.ac.uk/pub/databases/pdb/data/structures/divided/mmCIF/%s/%s.cif.gz'
# clean mmcif
updated_ftp = 'https://www.ebi.ac.uk/pdbe/static/entry/%s_updated.cif.gz'

# dictionaries
stored.domain_dict = {}
stored.seq_scheme = {}
stored.molecule_dict = {}
stored.poly_count = 0
stored.residue_dict = {}
stored.ca_p_only = []
stored.assemblies = {}
stored.operators = {}
stored.cif_items = {}
stored.asym_to_chain = {}
stored.assembly_objects = {}
stored.entities = {}

sphere_scale_dict = {'sticks': '0.25',
                     'spheres': '0.5',
                     'cartoon': '',
                     'ribbon': ''}

pdb_id_re = re.compile(r'\d[A-z0-9]{3}')
mmCIF_file_RE = re.compile(r'mmCIF_file=(.*)')
logging_RE = re.compile(r'logging=(.*)')

# cmd.set('connect_mode', 4)

empty_cif_list = ["", ".", "?", None]


class ApiCall:
    """functions specific to API calls"""

    def __init__(self, url):
        self.url = url
        self.data = {}

    def return_data(self):
        try:
            import requests
        except Exception as e:
            logging.error(e)
            return self.data
        self.encode_url()
        r = requests.get(url=self.url, timeout=60)
        if r.status_code == 200:
            json_data = r.json()
            self.data = json_data
        elif r.status_code == 404:
            self.data = {}

        else:
            logging.info(r.status_code, r.reason)
            self.data = {}

        return self.data

    def encode_url(self):
        self.url = re.sub(" ", "%20", self.url)


# url handling
def url_response_urllib2(url, description):
    """try several times to get a response from the API"""
    data = None
    try:
        import urllib2
    except Exception as e:
        logging.error(e)
        return data
    data_response = False
    tries = 1
    limit = 5
    logging.debug(url)
    date = datetime.datetime.now().strftime("%Y,%m,%d  %H:%M")
    while tries < limit:
        try:
            response = urllib2.urlopen(url, None, 60)
        except urllib2.HTTPError as e:
            logging.debug("##############")
            logging.debug("%s HTTP API error - %s, error code - %s, try %s" % (date, description, e.code, str(tries)))
            # logging.debug(e.code)
            if e.code == 404:
                data_response = True
                data = {}
                break
            else:
                # logging.debug(entry_url)
                time.sleep(random.randint(1, 20))  # sleep 1-20 seconds
                tries += 1
                logging.debug(e)
                data = {}
        except urllib2.URLError as e:
            logging.debug("##############")
            logging.debug("%s URL API error - %s, try %s" % (date, e, str(tries)))
            # logging.debug(entry_url)
            time.sleep(random.randint(1, 20))  # sleep 1-20 seconds
            tries += 1
            logging.debug(e)
            data = {}
        except socket.timeout as e:
            logging.debug("##############")
            logging.debug("%s Timeout API error - %s, try %s" % (date, e, str(tries)))
            # logging.debug(entry_url)
            time.sleep(random.randint(1, 20))  # sleep 1-20 seconds
            tries += 1
            logging.debug(e)
            data = {}
        else:
            logging.debug("received a response from the " + description + " API after " + str(tries) + " tries.")
            data = json.load(response)
            data_response = True
            break

    if not data_response:
        logging.debug("No response from the %s API" % description)
        # cmd.quit(1)

    return data


# url handling
def url_response(url, description):
    logging.debug(description)
    try:
        import requests
        data = ApiCall(url=url).return_data()
    except:
        data = url_response_urllib2(url=url, description=description)
    return data


def getColor(val, crange=[2, 5], inverted=1, absolute=1, buffer=32):
    """convert colour value in rgb for pymol"""
    if absolute == 1: val = abs(val)

    # Convert value to integer in range [0,510]
    integercolor = int((val - crange[0]) / (crange[1] - crange[0]) * 510)

    if integercolor < 0: integercolor = 0
    if integercolor > 510: integercolor = 510
    if inverted == 1: integercolor = 510 - integercolor

    # first 255 values are converted in color RED --> YELLOW
    if integercolor <= 255:
        red = 255 - buffer
        green = int(integercolor * (1 - buffer / 255))
        blue = 0
    # other values are converted in color YELLOW --> GREEN
    elif (integercolor <= 510):
        integercolor -= 255
        red = int(255 + integercolor * (buffer / 255 - 1))
        green = 255 - buffer
        blue = 0
    else:
        red = 150
        green = 150
        blue = 150

    red = float(red) / 255.0
    green = float(green) / 255.0
    blue = float(blue) / 255.0
    # return color format used for drawing in Pymol
    colour_list = []
    colour_list.append(red)
    colour_list.append(green)
    colour_list.append(blue)
    return colour_list
    # return "[" + int(red) + ',' + int(green) + ',' + int(blue) + "]"


pymolcolours = [
    "red", "green", "blue", "yellow", "magenta", "cyan",
    "tv_red", "tv_green", "tv_blue", "tv_yellow", "lightmagenta", "palecyan",
    "raspberry", "chartreuse", "marine", "paleyellow", "hotpink", "aquamarine",
    "darksalmon", "splitpea", "slate", "yelloworange", "pink", "greencyan",
    "salmon", "smudge", "lightblue", "limon", "lightpink", "teal",
    "deepsalmon", "palegreen", "skyblue", "wheat", "dirtyviolet", "deepteal",
    "warmpink", "limegreen", "purpleblue", "sand", "violet", "lightteal",
    "firebrick", "lime", "deepblue", "violetpurple",
    "ruby", "limon", "density", "purple",
    "chocolate", "forest", "deeppurple",
    "brown",
]

validation_background_colour = [0.4, 1.0, 0.4]
cmd.set_color("validation_green_background", validation_background_colour)
validation_colours = ['yellow', 'orange', 'red']
angle_bond_dict = {'angles': {'description': 'bond angles', 'colour': 'yellow', 'display': 'spheres'},
                   'bonds': {'description': 'bond length', 'colour': 'red', 'display': 'spheres'}}
rama_dict = {'ramachandran_outliers': {'selection': ' and name C+CA+N+O', 'colour': 'yellow', 'display': 'spheres'},
             'sidechain_outliers': {'selection': ' and not name N+CA+C+O', 'colour': 'red', 'display': 'spheres'}}


def colour_return(num):
    colournum = ""
    factor = 1
    while (num >= len(pymolcolours)):
        # logging.debug(num)
        num = num - (len(pymolcolours) * factor)
        # logging.debug(num)
        factor = factor + 1
    else:
        colournum = num
    colour = pymolcolours[colournum]
    return colour


def poly_display_type(asym, mol_type, length):
    """return either ribbon or cartoon depending on number of polymer chains"""
    ##start with it being cartoon - then change as needed.
    display_type = "cartoon"
    if stored.poly_count > 50:
        display_type = "ribbon"
    elif asym in stored.ca_p_only:
        logging.info('set ribbon trace on')
        cmd.set('ribbon_trace_atoms', 1)
        display_type = "ribbon"
    else:
        if re.search('polypeptide', mol_type):
            if length < 20:
                display_type = 'sticks'
        if re.search('nucleotide', mol_type):
            if length < 3:
                display_type = 'sticks'
        if re.search('saccharide', mol_type):
            display_type = 'sticks'

    # logging.debug('asym: %s, mol_type: %s, length: %s, display_type: %s' %(asym, mol_type, length, display_type))
    return display_type


class worker_functions():
    def trans_setting(self, selection, trans_value):
        cmd.set("cartoon_transparency", trans_value, selection)
        cmd.set("ribbon_transparency", trans_value, selection)
        cmd.set("stick_transparency", trans_value, selection)
        cmd.set("sphere_transparency", trans_value, selection)

    def count_poly(self, pdbid):
        url = moleculesURL + pdbid
        # global molecule_dict
        if stored.molecule_dict == {}:
            stored.molecule_dict = url_response(url, 'molecules')
        if pdbid in stored.molecule_dict:
            for entity in stored.molecule_dict[pdbid]:
                # add ca only list
                if entity['ca_p_only'] != False:
                    for a in entity['in_struct_asyms']:
                        if a not in stored.ca_p_only:
                            stored.ca_p_only.append(a)
                if entity['molecule_type'] not in ['water', 'bound']:
                    stored.poly_count += 1


def poly_seq_scheme(pdbid):
    """build a dictionary like poly_seq_scheme"""
    url = poly_seq_schemeURL + pdbid
    data = url_response(url, 'seq_scheme')
    if pdbid in data:
        for entity in data[pdbid]['molecules']:
            for chain in entity['chains']:
                chain_id = chain['chain_id']
                asym_id = chain['struct_asym_id']
                for residue in chain['residues']:
                    CIFnum = residue['residue_number']
                    PDBnum = residue['author_residue_number']
                    PDBinsCode = residue['author_insertion_code']
                    residueName = residue['residue_name']
                    if residue['observed_ratio'] != 0:
                        PDBobs = True
                    else:
                        PDBobs = False

                    stored.seq_scheme.setdefault(asym_id, {})[CIFnum] = {'PDBnum': PDBnum, 'PDBinsCode': PDBinsCode,
                                                                         'observed': PDBobs, 'residueName': residueName,
                                                                         'chainID': chain_id}


def asym_from_entity(pdbid, entity_id):
    url = moleculesURL + pdbid
    # global molecule_dict
    if stored.molecule_dict == {}:
        stored.molecule_dict = url_response(url, 'molecules')
    asym_id_list = []
    if pdbid in stored.molecule_dict:
        # logging.debug(entity_id)
        for entity in stored.molecule_dict[pdbid]:
            # add ca only list
            if entity['ca_p_only'] != False:
                for a in entity['in_struct_asyms']:
                    if a not in stored.ca_p_only:
                        stored.ca_p_only.append(a)
            # logging.info(entity['entity_id'])
            for a in entity['in_struct_asyms']:
                if str(entity_id) == str(entity['entity_id']):
                    asym_id_list.append(str(a))
    # logging.debug(asym_id_list)
    return asym_id_list


def check_range_observed(asym_id, start, end, unobs):
    range_dict = []
    firstResidue = 1
    lastResidue = 1
    for r in stored.seq_scheme[asym_id]:
        if r <= firstResidue:
            firstResidue = r
        if r >= lastResidue:
            lastResidue = r

    if end > lastResidue:
        # logging.debug('ERROR: residue %s from SIFTS is greater than the lastSeqRes number %s' %(end, lastSeqRes))
        end = lastResidue

    # logging.debug("first residue: %s, last residue %s" %(firstResidue, lastResidue))
    # logging.debug(seq_scheme[asym_id][start])
    if start in stored.seq_scheme[asym_id]:
        chain = stored.seq_scheme[asym_id][start]['chainID']

        while stored.seq_scheme[asym_id][start]['observed'] == False:
            # logging.debug("PDB start is not observed, adding 1 to residue number %s" %(start))
            if start == lastResidue:
                # logging.debug("domain not observed")
                unobs = True
                break
            else:
                start += 1
                if start == lastResidue:
                    # logging.debug("domain not observed")
                    unobs = True
                    break
                elif start == end:
                    # logging.debug("domain not observed")
                    unobs = True
                    break

    if end in stored.seq_scheme[asym_id]:
        while stored.seq_scheme[asym_id][end]['observed'] == False:
            # logging.debug("PDB end is not observed, minusing 1 from residue number %s" %(end))
            if end == firstResidue:
                # logging.debug("domain not observed")
                unobs = True
                break
            else:
                end -= 1
                if end == firstResidue:
                    # logging.debug("domain not observed")
                    unobs = True
                    break
                elif start == end:
                    # logging.debug("domain not observed")
                    unobs = True
                    break

    if unobs == False:
        # logging.debug("CIF start: %s, CIF end %s" %(start, end))
        # logging.debug("PDB start: %s, PDB end %s" %(PDBstart, PDBend))

        # need to do something about non continuous ranges which pymol doesn't cope with.
        """find all sections where the residue number increases by one. If it jumps then store this as a separate
        residue block while number is less than endbegin with number = start plus 1. see how the numbering differs
        from startif its 1 then its continuous - move to the next residue
        if its zero then there must be insert codes - this is ok - move to the next residue
        if its greater than 1 then store the previous residues as a block.
        """
        currentCIF = start
        blockStartCIF = start
        nextCIF = start + 1
        while nextCIF < end:
            currentPDB = stored.seq_scheme[asym_id][currentCIF]['PDBnum']
            nextPDB = stored.seq_scheme[asym_id][nextCIF]['PDBnum']
            if currentPDB not in empty_cif_list:
                if nextPDB in empty_cif_list:
                    startPDB = stored.seq_scheme[asym_id][blockStartCIF]['PDBnum']
                    swap = checkOrder(startPDB, currentPDB)
                    startPDBins = insert_code(asym_id, blockStartCIF)
                    currentPDB = insert_code(asym_id, currentCIF)
                    if swap == False:
                        range_dict.append({"PDBstart": startPDBins, "PDBend": currentPDB, "chainID": chain})
                    else:
                        range_dict.append({"PDBstart": currentPDB, "PDBend": startPDBins, "chainID": chain})
                    # move start to next block
                    blockStartCIF = nextCIF

                else:
                    currentPDB = int(stored.seq_scheme[asym_id][currentCIF]['PDBnum'])
                    nextPDB = int(stored.seq_scheme[asym_id][nextCIF]['PDBnum'])

                    if nextPDB - currentPDB > 1:
                        # logging.debug("numbering not continues, positive jump - store as section")
                        startPDB = stored.seq_scheme[asym_id][blockStartCIF]['PDBnum']
                        swap = checkOrder(startPDB, currentPDB)
                        startPDBins = insert_code(asym_id, blockStartCIF)
                        currentPDB = insert_code(asym_id, currentCIF)
                        if swap == False:
                            range_dict.append({"PDBstart": startPDBins, "PDBend": currentPDB, "chainID": chain})
                        else:
                            range_dict.append({"PDBstart": currentPDB, "PDBend": startPDBins, "chainID": chain})
                            # move start to next block
                        blockStartCIF = nextCIF
                    elif currentPDB - nextPDB > 1:
                        # logging.debug("numbering not continues, negative jump - store as section")
                        startPDB = stored.seq_scheme[asym_id][blockStartCIF]['PDBnum']
                        swap = checkOrder(startPDB, currentPDB)
                        startPDBins = insert_code(asym_id, blockStartCIF)
                        currentPDB = insert_code(asym_id, currentCIF)
                        if swap == False:
                            range_dict.append({"PDBstart": startPDBins, "PDBend": currentPDB, "chainID": chain})
                        else:
                            range_dict.append({"PDBstart": currentPDB, "PDBend": startPDBins, "chainID": chain})
                        # move start to next block
                        blockStartCIF = nextCIF
            else:
                blockStartCIF = nextCIF
            nextCIF += 1
            currentCIF += 1

        startPDB = stored.seq_scheme[asym_id][blockStartCIF]['PDBnum']
        swap = checkOrder(blockStartCIF, nextCIF)
        startPDBins = insert_code(asym_id, blockStartCIF)
        nextPDB = insert_code(asym_id, nextCIF)
        if swap == False:
            range_dict.append({"PDBstart": startPDBins, "PDBend": nextPDB, "chainID": chain})
        else:
            range_dict.append({"PDBstart": nextPDB, "PDBend": startPDBins, "chainID": chain})

            # logging.info(range_dict)
    else:
        logging.info("domain unobserved")

    return range_dict


def checkOrder(start, end):
    swap = False
    # logging.debug('PRE: start: %s, end %s, swap %s' %(start, end, swap))
    if type(start) is str:
        start = start.split('\\')[-1]
    if type(end) is str:
        end = end.split('\\')[-1]

    if int(start) > int(end):
        swap = True
    # logging.debug('POST: start: %s, end: %s, swap %s' %(start, end, swap))
    return swap


def insert_code(asym_id, CIFnum):
    if stored.seq_scheme[asym_id][CIFnum]['PDBinsCode'] == None:
        PDBnum = stored.seq_scheme[asym_id][CIFnum]['PDBnum']
    else:
        PDBnum = "%s%s" % (
            stored.seq_scheme[asym_id][CIFnum]['PDBnum'], stored.seq_scheme[asym_id][CIFnum]['PDBinsCode'])

    if re.search('-', str(PDBnum)):
        PDBnum = re.sub('-', '\-', str(PDBnum))

    return PDBnum


polymeric_types = ['']


class Validation:
    def launch_validation(self, pdbid):

        url = validationURL + pdbid
        val_data = url_response(url, 'validation')

        if val_data:
            logging.info('There is validation for this entry')

            url = validation_residueURL + pdbid
            res_data = url_response(url, 'residue validation')

            url = validation_ramaURL + pdbid
            rama_data = url_response(url, 'rama validation')

            self.per_residue_validation(pdbid, res_data, rama_data)
        else:
            logging.info("No validation for this entry")

            ###this takes too long for really large entries.
            # Validation().per_chain_per_residue_validation(pdbid, res_data, rama_data)

    """validation of all polymeric enties"""

    def validation_selection(self, selection, display_id):
        # logging.debug(selection)

        # uses a list so 0 means that there is one outlier for this residue.

        if selection in stored.residue_dict:
            colour_num = stored.residue_dict[selection] + 1
            stored.residue_dict[selection] = colour_num
        else:
            stored.residue_dict.update({selection: 0})
            colour_num = 0

        if colour_num > 2:
            colour_num = 2
        residue_colour = validation_colours[colour_num]
        # logging.debug(residue_colour)
        cmd.color(residue_colour, selection)

    def geometric_validation(self, pdbid, res_data, chain=False, model=1):
        """check for geometric validation outliers in res_data """

        if res_data:
            if pdbid in res_data:
                if 'molecules' in res_data[pdbid]:
                    if res_data[pdbid]['molecules']:
                        for entity in res_data[pdbid]['molecules']:
                            # logging.debug(entity)
                            entity_id = entity['entity_id']
                            for chain in entity['chains']:
                                chain_id = chain['chain_id']
                                # logging.debug(chain_id)
                                for model in chain['models']:
                                    model_id = int(model['model_id'])
                                    for outlier_type in model['outlier_types']:
                                        outliers = model['outlier_types'][outlier_type]
                                        # logging.debug(outlier_type)
                                        # logging.debug(outliers)
                                        for outlier in outliers:
                                            PDB_res_num = outlier['author_residue_number']
                                            PDB_ins_code = outlier['author_insertion_code']
                                            alt_code = outlier['alt_code']
                                            if PDB_ins_code not in [None, " "]:
                                                PDB_res_num = '%s%s' % (PDB_res_num, PDB_ins_code)

                                            # logging.debug(PDB_res_num)
                                            selection = "chain %s and resi %s" % (chain_id, PDB_res_num)
                                            if model == 1 or model_id:
                                                if chain == False or chain_id:
                                                    self.validation_selection(selection, pdbid)

                    else:
                        logging.info("no residue validation for this entry")

    def ramachandran_validation(self, pdbid, rama_data, chain=False, model=1):
        """display ramachandran outliers"""

        if rama_data:
            if pdbid in rama_data:
                for k in rama_data[pdbid]:
                    v = rama_data[pdbid][k]
                    if v:
                        logging.info("ramachandran %s for this entry" % k)
                        for outlier in rama_data[pdbid][k]:
                            # logging.debug(outlier)
                            entity_id = outlier['entity_id']
                            model_id = int(outlier['model_id'])
                            chain_id = outlier['chain_id']
                            PDB_res_num = outlier['author_residue_number']
                            PDB_ins_code = outlier['author_insertion_code']
                            alt_code = outlier['alt_code']

                            if PDB_ins_code not in [None, " "]:
                                PDB_res_num = '%s%s' % (PDB_res_num, PDB_ins_code)

                            selection = "chain %s and resi %s" % (chain_id, PDB_res_num)
                            if model == 1 or model_id:
                                if chain == False or chain_id:
                                    self.validation_selection(selection, pdbid)
                            else:
                                logging.info("is multimodel!!!, outlier not in model 1, not shown.")

                    else:
                        logging.info("no %s" % (k))

    def per_residue_validation(self, pdbid, res_data, rama_data):
        """validation of all outliers, coloured by number of outliers"""

        # display only polymers
        if stored.molecule_dict == {}:
            url = moleculesURL + pdbid
            stored.molecule_dict = url_response(url, 'molecules')
        if pdbid in stored.molecule_dict:
            for entity in stored.molecule_dict[pdbid]:
                # logging.info(entity)
                mol_type = entity['molecule_type']
                ca_only_list = []
                if entity['ca_p_only'] != False:
                    ca_only_list = entity['ca_p_only']
                if mol_type not in ['Water', 'Bound']:
                    for a in entity['in_struct_asyms']:
                        if stored.seq_scheme == {}:
                            poly_seq_scheme(pdbid)
                        unobs = False
                        start = 1
                        end = entity['length']
                        length = entity['length']
                        asym_id = a
                        display_type = poly_display_type(asym_id, 'polypeptide', length)
                        # logging.debug(asym_id)
                        x = check_range_observed(asym_id, start, end, unobs)
                        if x:
                            for y in x:
                                start = y['PDBstart']
                                end = y['PDBend']
                                chain = y['chainID']
                                selection = "chain %s and resi %s-%s and %s" % (chain, start, end, pdbid)
                                # logging.debug(selection)
                                cmd.show(display_type, selection)

        cmd.colour("validation_green_background", pdbid)
        # display(pdbid, image_type)
        cmd.enable(pdbid)

        self.geometric_validation(pdbid, res_data)
        self.ramachandran_validation(pdbid, rama_data)

        # logging.info(stored.residue_dict)


def entities(pdbid):
    logging.info('Display entities')
    cmd.set("cartoon_transparency", 0.3, pdbid)
    cmd.set("ribbon_transparency", 0.3, pdbid)
    url = moleculesURL + pdbid
    num = 1
    if stored.molecule_dict == {}:
        stored.molecule_dict = url_response(url, 'molecules')
    if pdbid in stored.molecule_dict:
        for entity in stored.molecule_dict[pdbid]:
            entity_name = ''
            if entity['molecule_name']:
                if len(entity['molecule_name']) > 1:
                    for instance, mol in enumerate(entity['molecule_name']):
                        if mol != entity['molecule_name'][-1]:
                            mol = mol + "-"
                            entity_name += mol
                        else:
                            entity_name += mol
                    entity_name = entity_name + '_chimera'
                else:
                    entity_name = entity['molecule_name'][0]
            else:
                logging.info("No name from the API")
                entity_name = "entity_%s" % (entity['entity_id'])
            # logging.debug('entity %s: %s' %(entity['entity_id'], entity_name))

            # logging.debug(entity['entity_id'])
            # see if its polymeric
            mol_type = entity['molecule_type']
            # entity_name = entity['molecule_name']
            if entity_name:
                objectName = re.sub(' ', '_', entity_name)
                objectName = re.sub(r'\W+', "", objectName)
            else:
                objectName = "entity_%s" % (entity['entity_id'])
            # logging.debug(objectName)
            display_type = ""
            object_selection = []
            pymol_selection = ""
            if mol_type != 'Water':
                # use asym to find residue number and chain ID
                for a in entity['in_struct_asyms']:
                    if stored.seq_scheme == {}:
                        poly_seq_scheme(pdbid)
                    if mol_type == 'Bound':
                        # bound molecules have no CIFresidue number and this is defaulted to 1 in the API
                        # logging.debug(entity_name)
                        # logging.debug(stored.seq_scheme[a])
                        for res in stored.seq_scheme[a]:
                            # logging.debug(stored.seq_scheme[a][res])
                            short = stored.seq_scheme[a][res]
                            chain = short['chainID']
                            res = ""
                            display_type = 'spheres'
                            # logging.debug(short)
                            if short['PDBinsCode'] == None:
                                res = str(short['PDBnum'])
                            else:
                                res = str(short['PDBnum']) + short['PDBinsCode']
                            selection = "chain %s and resi %s and %s" % (chain, res, pdbid)
                            object_selection.append(selection)
                            # logging.debug(selection)
                    else:
                        # find the first and last residues
                        unobs = False
                        start = 1
                        end = entity['length']
                        asym_id = a
                        ###need to work out if cartoon is the right thing to display
                        length = entity['length']
                        display_type = poly_display_type(asym_id, mol_type, length)
                        # logging.debug(asym_id)
                        x = check_range_observed(asym_id, start, end, unobs)
                        # logging.debug(x)
                        if x:
                            for y in x:
                                start = y['PDBstart']
                                end = y['PDBend']
                                chain = y['chainID']
                                selection = "chain %s and resi %s-%s and %s" % (chain, start, end, pdbid)
                                # logging.debug(selection)
                                object_selection.append(selection)

                for o in object_selection:
                    if len(object_selection) > 1:
                        if o == object_selection[-1]:
                            pymol_selection += "(%s)" % (o)
                        else:
                            pymol_selection += "(%s) or " % (o)
                    else:
                        pymol_selection += "%s" % (o)

                stored.entities.setdefault(pdbid, {}) \
                    .setdefault('entity', {}) \
                    .setdefault(entity['entity_id'], {}) \
                    .setdefault('selection', {}).setdefault('selection_list', []).append(pymol_selection)

                stored.entities[pdbid]['entity'][entity['entity_id']]['selection']['display_type'] = display_type

                # logging.debug(pymol_selection)
                if len(objectName) > 250:
                    objectName = objectName[:249]
                cmd.select("test_select", pymol_selection)
                cmd.create(objectName, "test_select")
                # logging.debug(display_type)
                cmd.show(display_type, objectName)

                # colour by entity.
                colour = colour_return(int(entity['entity_id']))
                # logging.debug(colour)
                cmd.color(colour, objectName)

    cmd.delete("test_select")
    # cmd.show("cartoon", pdbid)


def show_assemblies(pdbid, mmCIF_file):
    """iterate through the assemblies and output images"""
    logging.info('Generating assemblies')
    # cmd.hide('everything')
    worker_functions().trans_setting('all', 0.0)

    try:
        assemblies = cmd.get_assembly_ids(pdbid)  # list or None
        logging.info(assemblies)
        if assemblies:
            for a_id in assemblies:
                logging.info("Assembly: %s" % (a_id))
                assembly_name = pdbid + '_assem_' + a_id
                logging.info(assembly_name)
                cmd.set('assembly', a_id)
                cmd.load(mmCIF_file, assembly_name, format='cif')
                logging.info('finished Assembly: %s' % (a_id))
    except:
        logging.info('pymol version does not support assemblies')


def mapping(pdbid):
    """make domain objects"""
    if not stored.seq_scheme:
        poly_seq_scheme(pdbid)
    domain_to_make = ['CATH', 'SCOP', 'Pfam', 'Rfam']
    segment_identifier = {'CATH': 'domain', 'SCOP': 'scop_id', 'Pfam': '', 'Rfam': ''}
    protein_url = protein_mappingURL + pdbid
    nucleic_url = nucleic_mappingURL + pdbid
    protein_domains = url_response(protein_url, "protein_domains")
    nucleic_domains = url_response(nucleic_url, "nucleic_domains")
    for data in [protein_domains, nucleic_domains]:
        if data == {}:
            logging.info("no domain information for this entry")
        else:
            for domain_type in data[pdbid]:
                if domain_type in domain_to_make:
                    for domain in data[pdbid][domain_type]:
                        if data[pdbid][domain_type][domain]['mappings']:
                            identifier = data[pdbid][domain_type][domain]['identifier']
                            # logging.debug(domain_type)
                            # logging.debug(domain)
                            for mapping in data[pdbid][domain_type][domain]['mappings']:
                                unobs = False
                                domain_name = ""
                                # check segment id
                                if 'segment_id' in mapping:
                                    domain_segment_id = mapping['segment_id']
                                else:
                                    # force it to be one if its missing
                                    domain_segment_id = 1
                                if segment_identifier[domain_type] in mapping:
                                    domain_name = str(mapping[segment_identifier[domain_type]])
                                # logging.debug("%s: %s" %(domain_name, domain_segment_id))

                                # then check it exits
                                start = mapping['start']['residue_number']
                                end = mapping['end']['residue_number']
                                chain = mapping['chain_id']
                                entity_id = mapping['entity_id']
                                asym_id = mapping['struct_asym_id']
                                if asym_id in stored.seq_scheme:
                                    x = check_range_observed(asym_id, start, end, unobs)
                                    if x:
                                        for y in x:
                                            start = y['PDBstart']
                                            end = y['PDBend']
                                            stored.domain_dict.setdefault(domain_type, {}) \
                                                .setdefault(domain, {}) \
                                                .setdefault(domain_name, []).append(
                                                {'asym_id': asym_id, 'chain': chain, 'start': start, 'end': end,
                                                 'entity_id': entity_id})


def domains(pdbid):
    mapping(pdbid)
    obj_dict = {}
    chain_dict = {}
    if stored.domain_dict:
        # logging.info(domain_dict)
        for domain_type in stored.domain_dict:
            for domain in stored.domain_dict[domain_type]:
                # logging.debug(domain)
                for instance in stored.domain_dict[domain_type][domain]:
                    asym_list = []
                    entity_list = []
                    # logging.debug(instance)
                    object_selection = []
                    pymol_selection = ""
                    for segment in stored.domain_dict[domain_type][domain][instance]:
                        PDBstart = segment['start']
                        PDBend = segment['end']
                        chain = segment['chain']
                        asym_id = segment['asym_id']
                        entity_id = segment['entity_id']

                        asym_list.append(asym_id)
                        entity_list.append(entity_id)
                        # chain_dict.update({asym_id: {'chain': chain, 'entity_id': entity_id}})

                        selection = "chain %s and resi %s-%s and %s" % (chain, PDBstart, PDBend, pdbid)
                        object_selection.append(selection)
                    for o in object_selection:
                        if len(object_selection) > 1:
                            if o == object_selection[-1]:
                                pymol_selection += "(%s)" % (o)
                            else:
                                pymol_selection += "(%s) or " % (o)
                        else:
                            pymol_selection += "%s" % (o)
                    # logging.debug(pymol_selection)
                    objectName = "%s_%s_%s" % (domain_type, domain, instance)
                    obj_dict.update({objectName: {'asym_list': asym_list, 'entity_list': entity_list}})
                    cmd.select("test_select", pymol_selection)
                    cmd.create(objectName, "test_select")

            num = 1
            # logging.debug(obj_dict)
            for obj in obj_dict:
                # logging.debug(obj)
                cmd.enable(obj)
                # domain can span multiple asym_id's, could be different type
                for i, a in enumerate(obj_dict[obj]['asym_list']):
                    entity_id = obj_dict[obj]['entity_list'][i]
                    length = None
                    for entity in stored.molecule_dict[pdbid]:
                        if entity_id == entity['entity_id']:
                            length = entity['length']
                    display_type = poly_display_type(a, 'polypeptide', length)
                    cmd.show(display_type, obj)
                    colour = colour_return(num)
                    # logging.debug(colour)
                    cmd.color(colour, obj)
                    num += 1

            cmd.delete("test_select")


def PDBe_startup(pdbid, method, mmCIF_file=None, file_path=None):
    if pdbid:
        pdbid = pdbid.lower()
    if mmCIF_file:
        filename = os.path.basename(mmCIF_file)
        if re.search('_', filename):
            pdbid = re.split('_', filename)[0].lower()
        else:
            pdbid = re.split('\.', filename)[0].lower()

    try:
        cmd.set('cif_keepinmemory')
    except:
        logging.info('version of pymol does not support keeping all cif items')

    # check the PDB code actually exists.
    url = summaryURL + pdbid
    summary = url_response(url, "summary")

    if summary:

        # clear the dictionaries
        stored.domain_dict = {}
        stored.seq_scheme = {}
        stored.molecule_dict = {}
        stored.residue_dict = {}

        logging.info('pdbid: %s' % (pdbid))
        mid_pdb = pdbid[1:3]

        obj_list = cmd.get_object_list('all')
        if pdbid not in obj_list:
            if mmCIF_file:
                file_path = mmCIF_file
            else:
                # if local file exists then use it
                if os.path.exists("%s.cif" % (pdbid)):
                    logging.info("CIF found in current directory")
                    file_path = "%s.cif" % (pdbid)
                else:
                    logging.info("fetching %s" % (pdbid))
                    try:
                        # connect mode 4 works only with version 1.7 of pymol
                        cmd.set('assembly', '')
                        file_path = updated_ftp % pdbid
                        logging.info('setting connect mode to mode 4')
                        cmd.set('connect_mode', 4)
                    except:
                        logging.info('pymol version does not support assemblies or connect mode 4')
                        file_path = ebi_ftp % (mid_pdb, pdbid)

            logging.info('File to load: %s' % file_path)
            cmd.load(file_path, pdbid, format="cif")
        cmd.hide("everything", pdbid)
        worker_functions().count_poly(pdbid)

        if method == "entity":
            entities(pdbid)
        if method == "domains":
            entities(pdbid)
            domains(pdbid)
        elif method == "validation":
            Validation().launch_validation(pdbid)
        elif method == 'assemblies':
            entities(pdbid)
            show_assemblies(pdbid, file_path)
        elif method == 'show_assembly':
            show_assemblies(pdbid, file_path)
        elif method == 'all':
            entities(pdbid)
            domains(pdbid)
            show_assemblies(pdbid, file_path)
            Validation().launch_validation(pdbid)
        else:
            logging.info("provide a method")
        cmd.zoom(pdbid, complete=1)

    elif mmCIF_file:
        logging.info('no PDB ID, show assemblies from mmCIF file')
        cmd.load(mmCIF_file, pdbid, format="cif")
        # worker_functions().count_poly(pdbid)
        show_assemblies(pdbid, mmCIF_file)

    else:
        logging.info("please provide a 4 letter PDB code")


def __init__(self):
    try:
        # Simply add the menu entry and callback
        self.menuBar.addmenuitem('Plugin', 'command', 'PDB Loader',
                                 label='PDB Analysis - All',
                                 command=lambda s=self: PDBeLoaderDialog(s))
        self.menuBar.addmenuitem('Plugin', 'command', 'PDB Molecules',
                                 label='PDB Analysis - Molecules',
                                 command=lambda s=self: PDBeEntityDialog(s))
        self.menuBar.addmenuitem('Plugin', 'command', 'PDB Domains',
                                 label='PDB Analysis - Domains',
                                 command=lambda s=self: PDBeDomainDialog(s))
        self.menuBar.addmenuitem('Plugin', 'command', 'PDB Validation',
                                 label='PDB Analysis - Validation',
                                 command=lambda s=self: PDBeValidationDialog(s))
        self.menuBar.addmenuitem('Plugin', 'command', 'Assemblies',
                                 label='PDB Analysis - Assemblies',
                                 command=lambda s=self: PDBeAssemblyDialog(s))

    except Exception as e:
        logging.error('unable to make menu items')
        logging.error(e)


def PDBeLoaderDialog(app):
    import tkSimpleDialog
    pdbCode = tkSimpleDialog.askstring('PDB Loader Service',
                                       'Highlight chemically distinct molecules, domains and assemblies in a PDB entry. Please enter a 4-digit pdb code:',
                                       parent=app.root)
    PDBe_startup(pdbCode, "all")


def PDBeEntityDialog(app):
    import tkSimpleDialog
    pdbCode = tkSimpleDialog.askstring('PDB Loader Service',
                                       'Highlight chemically distinct molecules in a PDB entry. Please enter a 4-digit pdb code:',
                                       parent=app.root)
    PDBe_startup(pdbCode, "entity")


def PDBeDomainDialog(app):
    import tkSimpleDialog
    pdbCode = tkSimpleDialog.askstring('PDB Loader Service',
                                       'Display Pfam, SCOP, CATH and Rfam domains on a PDB entry. Please enter a 4-digit pdb code:',
                                       parent=app.root)
    PDBe_startup(pdbCode, "domains")


def PDBeValidationDialog(app):
    import tkSimpleDialog
    pdbCode = tkSimpleDialog.askstring('PDB Loader Service',
                                       'Display geometric outliers on a PDB entry. Please enter a 4-digit pdb code:',
                                       parent=app.root)
    PDBe_startup(pdbCode, "validation")


def PDBeAssemblyDialog(app):
    import tkSimpleDialog
    pdbCode = tkSimpleDialog.askstring('PDB Loader Service',
                                       'Display assemblies for a PDB entry. Please enter a 4-digit pdb code:',
                                       parent=app.root)
    PDBe_startup(pdbCode, "show_assembly")


def PDBe_entities(pdbid):
    """launch PDBe entity"""
    PDBe_startup(pdbid, "entity")


def PDBe_domains(pdbid):
    PDBe_startup(pdbid, "domains")


def PDBe_validation(pdbid):
    PDBe_startup(pdbid, "validation")


def PDBe_assemblies(pdbid):
    PDBe_startup(pdbid, "show_assembly")


pymol.cmd.extend("PDB_Analysis_Molecules", PDBe_entities)
pymol.cmd.extend("PDB_Analysis_Domains", PDBe_domains)
pymol.cmd.extend("PDB_Analysis_Validation", PDBe_validation)
pymol.cmd.extend("PDB_Analysis_Assemblies", PDBe_assemblies)


def chain_append(chain):
    if chain not in stored.chain:
        pymol.stored.chain.append(chain)


def count_chain(selection):
    pymol.stored.chain = []
    pymol.cmd.iterate(selection, 'chain_append(chain)')
    logging.info(stored.chain)
    logging.info("Number of chains: %s" % (len(stored.chain)))


pymol.cmd.extend("count_chain", count_chain)


def usage():
    usage = """
        Usage
            pymol -r PDB_plugin.py -- mmCIF_file=MY_CIF_FILE.cif
            or 
            pymol -r PDB_plugin.py -- PDBID
        """
    logging.info(usage)
    # pymol.cmd.quit()



if __name__ == '__main__':
    mmCIF_file = None
    pdbid = None
    if len(sys.argv) > 1:
        logging.debug(sys.argv)
        for arr in sys.argv:
            if pdb_id_re.match(arr):
                pdbid = pdb_id_re.match(arr).group(0)
            if mmCIF_file_RE.match(arr):
                mmCIF_file = mmCIF_file_RE.match(arr).group(1)

        if pdbid or mmCIF_file:
            logging.info('pdbid: %s' % pdbid)
            logging.info('mmCIF file: %s' % mmCIF_file)
            PDBe_startup(pdbid, 'all', mmCIF_file=mmCIF_file)
        else:
            logging.info(usage())
else:
    logging.info(usage())
