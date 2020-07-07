#@ File (label="Select first CZI file", description="select only the first czi file")  input_path
#@ Integer (label="Downsample fused image", description="1 = full resolution", style="slider", min=1, max=20, stepSize=1, value=1) downsampling
#@ Boolean (label="convert fused image to Imaris5", description="convert to fused image to *.ims", value=true) convert_to_ims

# python imports
import os
import time

# Imagej imports
from ij import IJ

# requirements
# BigStitcher
# faim-imagej-imaris-tools-0.0.1.jar (https://maven.scijava.org/service/local/repositories/releases/content/org/scijava/faim-imagej-imaris-tools/0.0.1/faim-imagej-imaris-tools-0.0.1.jar)


def get_free_memory():
    """
    get the free memory in IJ in bytes
    """
    max_memory = int(IJ.maxMemory())
    used_memory = int(IJ.currentMemory())
    free_memory = max_memory - used_memory

    return free_memory

# get start time
execution_start_time = time.time()

# get filename and path names
input_path = str(input_path)
first_czi = input_path.replace("\\", "/")
filename = os.path.basename(input_path)
parent_dir = os.path.dirname(input_path)
parent_dir = parent_dir.replace("\\", "/")
project_filename = filename.replace(".czi", ".xml")
project_filename_short = filename.replace(".czi", "")
export_path = parent_dir + "/" + project_filename_short
project_path = parent_dir + "/" + project_filename
export_path_fused = parent_dir + "/" + project_filename_short + "_fused.xml"
bdv_file = export_path + ".h5"

# run BigStitcher
# define dataset
IJ.run("Define dataset ...", "define_dataset=[Automatic Loader (Bioformats based)] project_filename=" + project_filename +" path=" + first_czi + " exclude=10 bioformats_series_are?=Tiles move_tiles_to_grid_(per_angle)?=[Do not move Tiles to Grid (use Metadata if available)] how_to_load_images=[Re-save as multiresolution HDF5] dataset_save_path=" + parent_dir + " check_stack_sizes use_deflate_compression export_path=" + export_path)

# calculate pairwise shifts // at this step the views dual side illum can be averaged?
IJ.run("Calculate pairwise shifts ...", "select=" + project_path + " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] method=[Phase Correlation] channels=[Average Channels] illuminations=[Average Illuminations]")

# filter shifts with 0.7 corr. threshold
IJ.run("Filter pairwise shifts ...", "select=" + project_path + " filter_by_link_quality min_r=0.7 max_r=1 max_shift_in_x=0 max_shift_in_y=0 max_shift_in_z=0 max_displacement=0")

# do global optimization
IJ.run("Optimize globally and apply shifts ...", "select=" + project_path + " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] relative=2.500 absolute=3.500 global_optimization_strategy=[Two-Round using Metadata to align unconnected Tiles] fix_group_0-0,")

# select illuminations
# TODO: test quality if this is skipped. is quality better?
# TODO: test: if there is only one illumination side, is this part just omitted or is it an error?
IJ.run("Select Illuminations", "select=" + project_path + " selection=[Pick brightest]")

# check the file size of the newly written stitched h5 and compare to the available RAM
stitched_filesize = os.path.getsize(bdv_file)
free_memory = get_free_memory()

print("stitched_filesize " + str(stitched_filesize))
print("free memory in ij " + str(free_memory))

if free_memory > (1.94 * stitched_filesize / downsampling):
    ram_handling = "[Precompute Image]"
else:
    ram_handling = "Cached"

print("fusion mode used " + str(ram_handling))

# fuse dataset, save as new hdf5
IJ.run("Fuse dataset ...", "select=" + project_path + " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] bounding_box=[Currently Selected Views] downsampling=" + str(downsampling) + " pixel_type=[16-bit unsigned integer] interpolation=[Linear Interpolation] image=" + ram_handling + " interest_points_for_non_rigid=[-= Disable Non-Rigid =-] blend produce=[Each timepoint & channel] fused_image=[Save as new XML Project (HDF5)] use_deflate_compression export_path="+ export_path_fused)

# collect garbage
IJ.log("collecting garbage...")
IJ.run("Collect Garbage", "")
time.sleep(60.0)
IJ.run("Collect Garbage", "")
time.sleep(60.0)
IJ.run("Collect Garbage", "")
time.sleep(60.0)

# convert to Imaris5 format
imarisconvert = "C:/Program Files/Bitplane/Imaris x64 9.5.1/ImarisConvert.exe"
imarisconvert_alternative = "C:/Program Files/Bitplane/ImarisFileConverter 9.5.1/ImarisConvert.exe"
if os.path.exists(imarisconvert) == False:
    imarisconvert = imarisconvert_alternative

if convert_to_ims == True:
    IJ.log("converting to Imaris5 format...")
    IJ.run("Imaris Converter...", "imarisconvert=[" + imarisconvert + "]")
    IJ.run("Convert to Imaris5 format", "inputfile=" + export_path_fused + " delete=false")

total_execution_time_min = (time.time() - execution_start_time) / 60.0
IJ.log("total time in minutes: " + str(total_execution_time_min))
IJ.log("All done")