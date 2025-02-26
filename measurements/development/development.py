
import os
import re
import requests
import zipfile
import shutil
import pathlib
import klayout.db as pya
import siepicfab_ebeam_zep
import SiEPIC
from SiEPIC.utils import find_automated_measurement_labels
import matplotlib.pyplot as plt
import scipy.io
import sys
from SiEPIC.scripts import connect_pins_with_waveguide, connect_cell, zoom_out, export_layout
from SiEPIC.extend import get_LumericalINTERCONNECT_analyzers_from_opt_in
from SiEPIC.scripts import trim_netlist, trace_hierarchy_up_single

def load_layout_and_extract_labels():
    """
    Loads the layout file located at ../aggregate/Shuksan.oas and extracts opt_in labels using SiEPIC.
    
    Returns:
        list: Extracted opt_in labels from the layout.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    layout_path = os.path.abspath(os.path.join(script_dir, '..', 'aggregate', 'Shuksan.oas'))
    
    if not os.path.exists(layout_path):
        raise FileNotFoundError(f"Layout file not found at expected location: {layout_path}")
    
    # Load all the layouts, without the libraries (no PCells)
    disable_libraries()

    layout = pya.Layout()
    layout.read(layout_path)
    layout.technology_name = "SiEPICfab_EBeam_ZEP"
    
    top_cell = layout.top_cell()
    if not top_cell:
        raise RuntimeError("No top cell found in the layout.")
    
    labels = find_automated_measurement_labels(top_cell)
    print(f"Extracted number of labels: {len(labels[1])}")
    return layout, labels


def find_parent_cell_and_instance(layout, target_inst_array, verbose=False):
    """
    Given a pya.CellInstArray, find its parent cell and corresponding pya.Instance.

    :param layout: The pya.Layout object.
    :param target_inst_array: The pya.CellInstArray to find.
    :return: (parent_cell, instance) if found, else (None, None).
    """
    for cell in layout.each_cell():
        for inst in cell.each_inst():
            if inst.cell_inst.cell_index == target_inst_array.cell_index:
                if verbose:
                    print (f" **** compare found: {inst.cell.name}: {inst.cell_inst} {layout.cell(target_inst_array.cell_index).name}:{target_inst_array}")
                return cell, inst  # Found the instance and its parent cell

    return None, None  # Not found

def get_absolute_transformation(layout, inst, verbose=False):
    """
    Compute the absolute transformation of a cell instance relative to the top cell.
    
    :param inst: The pya.CellInstArray instance of the cell.
    :return: pya.ICplxTrans representing the absolute transformation.
    """
    # print(inst, type(inst))
    # cell, inst = find_parent_cell_and_instance(layout, inst)
    # print(inst, type(inst))
    transformation = pya.Trans()

    current_inst = inst
    while True:
        transformation *= current_inst.trans
        if verbose:
            print (f" current instance: {current_inst.cell.name}")
            print (f" parent instance: {current_inst.parent_cell.name}")
            print (f" cumulative transformation: {transformation}")
        each_parent_inst = current_inst.cell.each_parent_inst()
        parent_inst = next(each_parent_inst).inst()
        #if verbose:
        #    print (f" parent CellInstArray: {parent_inst} {type(parent_inst)}")
        cell, parent_inst = find_parent_cell_and_instance(layout, parent_inst)
        if not parent_inst:
            # No more parent instances found, we reached the top cell
            if verbose:
                print('break')
            break
        if verbose:
            print (f" parent Instance: {parent_inst.cell.name} {type(parent_inst)}")
        
        current_inst = parent_inst
        
    return transformation


def get_single_instance(layout, target_cell):
    """
    Finds and returns the single instance (pya.CellInstArray) of the given target cell.
    
    :param layout: The pya.Layout object.
    :param target_cell: The pya.Cell object to find the instance of.
    :return: The pya.CellInstArray instance containing the target cell, or None if not found or multiple instances exist.
    """
    instances = []

    # Iterate through all cells to find where the target_cell is instantiated
    for cell in layout.each_cell():
        for inst in cell.each_inst():
            if inst.cell == target_cell:
                instances.append(inst)

    # Ensure the target cell is only instantiated once
    if len(instances) == 1:
        return instances[0]
    elif len(instances) > 1:
        raise ValueError(f"Cell '{target_cell.name}' is instantiated multiple times. Expected only one instance.")
    else:
        return None  # Not found

def find_text_label(layout, layer_name, target_text):
    """
    Scans a layout file to find a specific text label on a given layer and returns the cell containing that text.
    
    Args:
        layout (pya.Layout): The layout object.
        layer_name (str): The layer name where the text is expected.
        target_text (str): The text label to find.
    
    Returns:
        pya.Cell: The cell containing the text, or None if not found.
    """
    layer_index = layout.layer(layer_name)
    if layer_index is None:
        raise Exception('Layer not found')
    
    iter = layout.top_cell().begin_shapes_rec(layer_index)
    while not iter.at_end():
        if iter.shape().is_text():
            text = iter.shape().text.string
            if text == target_text:
                # Ensure we return a non-Const cell, see issue: https://github.com/KLayout/klayout/issues/235
                return layout.cell(iter.cell().name) 
        iter.next()
    return None

def disable_libraries():
    print('Disabling KLayout libraries')
    for l in pya.Library().library_ids():
        print(' - %s' % pya.Library().library_by_id(l).name())
        pya.Library().library_by_id(l).delete()
    
def match_files_with_labels(mat_files_dir, labels):
    """
    Matches .mat files in the mat_files directory with the extracted opt_in labels.
    
    Args:
        mat_files_dir (str): The directory containing .mat files.
        labels (list): Extracted opt_in labels from the layout.
    
    Returns:
        dict: A mapping of labels to matching .mat files.
    """
    matches = {}
    for root, _, files in os.walk(mat_files_dir):
        for label in labels[1]:
            device_id = label.get('deviceID', '')
            params = "_".join(label.get('params', []))
            expected_folder_start = f"{device_id}_{params}".strip('_')

            if os.path.basename(root).startswith(expected_folder_start):
                for file in files:
                    if file.endswith(".mat"):
                        matches.setdefault(expected_folder_start, []).append(os.path.join(root, file))
                        matches[expected_folder_start].append(label)
    
    print(f"Matched files: {len(matches)}")
    return matches

def extract_layout_using_opt_in(layout, opt_in_text, layout2=None):
    '''
    Extract the layout for a circuit connected to an opt_in label
    
    Layout: to scan for the opt_in label
    opt_in_text: <str>
    layout2: optionally, add to an existing layout
    
    Returns:
    pya.Cell: the new cell
    pya.Layout: the new layout

    '''
    # configure the destination layout and top cell
    if not layout2:
        layout2=pya.Layout()
    if layout2.cell('top'):
        topcell2 = layout2.cell('top')
    else:
        topcell2=layout2.create_cell('top')

    # Find the cell that contains the label
    cell = find_text_label(layout, [10,0], opt_in_text)
    print(f" cell containing opt_in: {cell.name}")
    # Find the transformation for the opt_in label within the cell, versus top cell
    inst = get_single_instance(layout, cell)
    transformation = get_absolute_transformation(layout, inst)
    # print(f" transformation 2:  {transformation}")

    # get the netlist from the entire layout
    try:
        nets, components = cell.identify_nets()
    except:
        return topcell2, layout2
    
    # using opt_in, identify where the laser and detectors are connected
    # this updates the Optical IO Net
    laser_net, detector_nets, *_ = get_LumericalINTERCONNECT_analyzers_from_opt_in(
        cell, components, opt_in_selection_text=[opt_in_text])
    if not laser_net or not detector_nets:
        raise Exception('opt_in label did not yield laser/detectors.')

    # trim the netlist, based on where the laser is connected
    laser_component = [c for c in components if any(
        [p for p in c.pins if p.type == SiEPIC._globals.PIN_TYPES.OPTICALIO and 'laser' in p.pin_name])]
    nets, components = trim_netlist(nets, components, laser_component[0])
        
    # recreate the layout, copying cells and shapes
    for c in components:
        cell1 = layout2.create_cell(c.cell.name)
        cells1 = cell1.copy_tree(layout.cell(c.cell.name)) 
        # print(f" trans: {c.trans} {transformation}")
        #print(f" trans type: {type(c.trans)} {type(transformation)}")
        topcell2.insert(pya.CellInstArray(cell1.cell_index(), pya.ICplxTrans(transformation) * c.trans))   
    layout3 = pya.Layout()
    topcell3 = layout3.create_cell('top')
    topcell3.copy_shapes(cell)
    topcell3.transform(transformation)
    topcell2.copy_shapes(topcell3)

    return topcell2, layout2

    
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if 1:
        # Copy the layout for a circuit connected to an opt_in label
        layout, labels = load_layout_and_extract_labels()
        mat_path = os.path.join(script_dir,'mat_files')
        matches = match_files_with_labels(mat_path, labels)
        layout2 = pya.Layout()
        for m in matches:
#            if 'Itaiboss' in m:
            #if 'MZI' in m:
            if 'petervoznyuk_' in m or 'Itaiboss' in m:
                # print(matches[m])
                #analyze_mat_file(matches[m][0],m)
                
                opt_in_text = matches[m][1]['opt_in']
                print(f' opt_in: {opt_in_text}')
                
                cell2, layout2 = extract_layout_using_opt_in(layout, opt_in_text, layout2=layout2)

                filename = 'development' # top_cell_name
                file_out = export_layout(cell2, script_dir, filename, relative_path = '.', format='oas', screenshot=True)

                    

