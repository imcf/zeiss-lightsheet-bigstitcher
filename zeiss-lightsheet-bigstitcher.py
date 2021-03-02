#@ File (label="Select first CZI file", description="select only the first czi file")  input_path
#@ Boolean (label="Automatically select best illumination side", description="discard the other illumination", value=false) autoselect_illuminations
#@ Boolean (label="Fuse image", description="saves a separate fused h5/xml", value=true) fuse
#@ File (label="Select a temp directory", style="directory", description="choose a local drive with enough space, e.g. S: on VAMP or D: on a desktop workstation") temp_directory
#@ Integer (label="Downsample fused image", description="1 = full resolution", style="slider", min=1, max=20, stepSize=1, value=1) downsampling
#@ Boolean (label="Convert fused image to Imaris5", description="convert to fused image to *.ims", value=true) convert_to_ims
#@ String (label="Send info email to: ", description="empty = skip") email_address


# python imports
import os
import time
import smtplib
import shutil

# Imagej imports
from ij import IJ

# requirements:
# BigStitcher, Multiview Reconstruction >= 10.2
# faim-imagej-imaris-tools-0.0.1.jar (https://maven.scijava.org/service/local/repositories/releases/content/org/scijava/faim-imagej-imaris-tools/0.0.1/faim-imagej-imaris-tools-0.0.1.jar)


def get_free_memory():
    """gets the free memory thats available to ImageJ

    Returns
    -------
    free_memory : integer
        the free memory in bytes
    """
    max_memory = int(IJ.maxMemory())
    used_memory = int(IJ.currentMemory())
    free_memory = max_memory - used_memory

    return free_memory


def send_mail( sender, recipient, filename, total_execution_time_min ):
    """send an email via smtp.unibas.ch. 
    Will likely NOT work without connection to the unibas network. 

    Parameters
    ----------
    sender : string
        senders email address
    recipient : string
        recipients email address
    filename : string
        the name of the file to be passed in the email
    total_execution_time_min : float
        the time it took to process the file
    """

    header  = "From: imcf@unibas.ch\n"
    header += "To: %s\n"
    header += "Subject: Your Lightsheet processing job finished successfully\n\n"
    text = "Dear recipient,\n\n"\
    "This is an automated message from the Zeiss Lightsheet BigStitcher.\n"\
    "Your file %s has been successfully processed (%s min).\n\n"\
    "Kind regards,\n"\
    "The IMCF-team"
    
    message = header + text

    try:
       smtpObj = smtplib.SMTP("smtp.unibas.ch")
       smtpObj.sendmail( sender, recipient, message % ( recipient, filename, total_execution_time_min ) )
       print "Successfully sent email"
    except SMTPException:
       print "Error: unable to send email"

       
# get start time
execution_start_time = time.time()

# get filename and path names
# TODO: this seems messy and might be possible with less variables / steps
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
# define_dataset (Zeiss Lightsheet Z.1 Dataset Loader)
IJ.run(
    "Define dataset ...", 
    "define_dataset=[Zeiss Lightsheet Z.1 Dataset Loader (Bioformats)] " + 
    "project_filename=[" + project_filename +"] " + 
    "first_czi=[" + first_czi + "] " + 
    "apply_rotation_to_dataset " + 
    "fix_bioformats"
)

# resave as h5/xml
IJ.run(
    "As HDF5 ...", 
    "select=[" + project_path + "] " + 
    "resave_angle=[All angles] " + 
    "resave_channel=[All channels] " + 
    "resave_illumination=[All illuminations] " + 
    "resave_tile=[All tiles] " + 
    "resave_timepoint=[All Timepoints] " + 
    "use_deflate_compression " + 
    "export_path=[" + export_path + "]"
)

# calculate pairwise shifts
IJ.run(
    "Calculate pairwise shifts ...", 
    "select=[" + project_path + "] " + 
    "process_angle=[All angles] " + 
    "process_channel=[All channels] " + 
    "process_illumination=[All illuminations] " + 
    "process_tile=[All tiles] " + 
    "process_timepoint=[All Timepoints] " + 
    "method=[Phase Correlation] " + 
    "channels=[Average Channels] " + 
    "illuminations=[Average Illuminations]"
)

# filter shifts with 0.7 corr. threshold
IJ.run(
    "Filter pairwise shifts ...", 
    "select=[" + project_path + "] " + 
    "filter_by_link_quality " + 
    "min_r=0.7 " + 
    "max_r=1 " + 
    "max_shift_in_x=0 " + 
    "max_shift_in_y=0 " + 
    "max_shift_in_z=0 " + 
    "max_displacement=0"
)

# do global optimization
IJ.run(
    "Optimize globally and apply shifts ...", 
    "select=[" + project_path + "] " + 
    "process_angle=[All angles] " + 
    "process_channel=[All channels] " + 
    "process_illumination=[All illuminations] " + 
    "process_tile=[All tiles] " + 
    "process_timepoint=[All Timepoints] " + 
    "relative=2.500 " + 
    "absolute=3.500 " + 
    "global_optimization_strategy=[Two-Round using Metadata to align unconnected Tiles] " + 
    "fix_group_0-0,"
)

# select illuminations
if autoselect_illuminations == True:
    IJ.run(
        "Select Illuminations", 
        "select=[" + project_path + "] " + 
        "selection=[Pick brightest]"
    )

# TODO: introduce option for auto bounding box function

if fuse == True:
    # check the file size of the file to be fused and compare to the available RAM
    stitched_filesize = os.path.getsize(bdv_file)
    free_memory = get_free_memory()

    print("stitched_filesize " + str(stitched_filesize))
    print("free memory in ij " + str(free_memory))

    # TODO: include in below calculation downsampling * t_end, since only one t is fused at a time.
    if free_memory > (1.94 * stitched_filesize / downsampling):
        ram_handling = "[Precompute Image]"
    else:
        ram_handling = "Cached"
    print("fusion mode used " + str(ram_handling))

    # fuse dataset, save as new hdf5
    # re-save as xml/tiff first in a temp location and fuse the xml/tiff instead, since fusing from an h5/xml is really slow
    temp = str(temp_directory).replace("\\", "/") + "/temp"
    if not os.path.exists(temp):
        os.mkdir(temp)
    temp_path = temp + "/" + project_filename
    IJ.run(
        "As TIFF ...", 
        "select=[" + project_path + "] " + 
        "resave_angle=[All angles] " + 
        "resave_channel=[All channels] " + 
        "resave_illumination=[All illuminations] " + 
        "resave_tile=[All tiles] " + 
        "resave_timepoint=[All Timepoints] " + 
        "export_path=[" + temp_path + "]"
    )

    IJ.run(
        "Fuse dataset ...", 
        "select=[" + temp_path + "] " + 
        "process_angle=[All angles] " + 
        "process_channel=[All channels] " + 
        "process_illumination=[All illuminations] " + 
        "process_tile=[All tiles] " + 
        "process_timepoint=[All Timepoints] " + 
        "bounding_box=[Currently Selected Views] " + 
        "downsampling=" + str(downsampling) + " " + 
        "pixel_type=[16-bit unsigned integer] " + 
        "interpolation=[Linear Interpolation] " + 
        "image=" + ram_handling + " " + 
        "interest_points_for_non_rigid=[-= Disable Non-Rigid =-] " + 
        "blend produce=[Each timepoint & channel] " + 
        "fused_image=[Save as new XML Project (HDF5)] " + 
        "use_deflate_compression " + 
        "export_path=["+ export_path_fused + "]"
    )

    shutil.rmtree(temp, ignore_errors = True) # remove temp folder

# free memory in IJ
IJ.log("collecting garbage...")
IJ.run("Collect Garbage", "")
time.sleep(60.0)
IJ.run("Collect Garbage", "")
time.sleep(60.0)
IJ.run("Collect Garbage", "")
time.sleep(60.0)

# convert to Imaris5 format
imarisconvert = "C:/Program Files/Bitplane/Imaris x64 9.6.0/ImarisConvert.exe"
imarisconvert_alternative = "C:/Program Files/Bitplane/ImarisFileConverter 9.6.0/ImarisConvert.exe"
if os.path.exists(imarisconvert) == False:
    imarisconvert = imarisconvert_alternative

if fuse == True and convert_to_ims == True:
    IJ.log("converting to Imaris5 format...")
    IJ.run("Imaris Converter...", "imarisconvert=[" + imarisconvert + "]")
    IJ.run("Convert to Imaris5 format", "inputfile=[" + export_path_fused + "] delete=false")

total_execution_time_min = round( (time.time() - execution_start_time) / 60.0 )

if email_address != "":
    send_mail( "imcf@unibas.ch", email_address, filename, total_execution_time_min )
else:
    print "Email address field is empty, no email was sent"

IJ.log("\n~~~ Job summary ~~~")
IJ.log("Filename: " + str( filename ))
IJ.log("Automatically select best illumination side: " + str( autoselect_illuminations ))
IJ.log("Fuse image: " + str( fuse ))
IJ.log("Downsample fused image: " + str( downsampling ))
IJ.log("Path for temporary image files: " + str( temp_directory ))
IJ.log("Convert fused image to Imaris5: " + str( convert_to_ims ))
IJ.log("Send info email to: " + str( email_address ))
IJ.log("Total time in minutes: " + str( total_execution_time_min ))
IJ.log("All done")
IJ.selectWindow("Log")
IJ.saveAs("Text", str(first_czi) + "_BigStitcher_Log")
