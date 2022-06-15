# ─── SCRIPT PARAMETERS ──────────────────────────────────────────────────────────

#@ File (label="Select first CZI file", description="select only the first czi file")  input_path
#@ String (label="What reader to use ?", choices={"LightSheet 7 (Zen tiling)","LightSheet Z.1 / 7 (Tile scan macro)"}, style="listBox") reader
#@ Boolean (label="Automatically select best illumination side", description="discard the other illumination", value=false) autoselect_illuminations
#@ Boolean (label="Fuse image", description="saves a separate fused h5/xml", value=true) fuse
#@ File (label="Select a temp directory", style="directory", description="choose a local drive with enough space, e.g. S: on VAMP or D: on a desktop workstation") temp_directory
#@ Integer (label="Downsample fused image", description="1 = full resolution", style="slider", min=1, max=20, stepSize=1, value=1) downsampling
#@ Boolean (label="Convert fused image to Imaris5", description="convert to fused image to *.ims", value=true) convert_to_ims
#@ String (label="Send info email to: ", description="empty = skip") email_address

# TODO: include tp range request by default, maybe in two variables, t_start and t_end. Then use them instead of "[All Timepoints]"

# ─── IMPORTS ────────────────────────────────────────────────────────────────────

# python imports
import os
import glob
import time
import smtplib
import shutil

# Imagej imports
from ij import IJ

# requirements:
# BigStitcher, Multiview Reconstruction >= 10.2
# faim-imagej-imaris-tools-0.0.1.jar (https://maven.scijava.org/service/local/repositories/releases/content/org/scijava/faim-imagej-imaris-tools/0.0.1/faim-imagej-imaris-tools-0.0.1.jar)

# ─── FUNCTIONS ──────────────────────────────────────────────────────────────────

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
    text = (
        "Dear recipient,\n\n"
        "This is an automated message from the Zeiss Lightsheet Multiview Reconstruction tool.\n"
        "Your file %s has been successfully processed (%s min).\n\n"
        "Kind regards,\n"
        "The IMCF-team"
    )

    message = header + text

    try:
       smtpObj = smtplib.SMTP("smtp.unibas.ch")
       smtpObj.sendmail( sender, recipient, message % ( recipient, filename, total_execution_time_min ) )
       print("Successfully sent email")
    except smtplib.SMTPException:
       print("Error: unable to send email")

def locate_latest_imaris(paths_to_check=None):
    """Find paths to latest installed Imaris or ImarisFileConverter version.

    Parameters
    ----------
    paths_to_check: list of str, optional
        A list of paths that should be used to look for the installations, by default
        `None` which will fall back to the standard installation locations of Bitplane.

    Returns
    -------
    str
        Full path to the most recent (as in "version number") ImarisFileConverter
        or Imaris installation folder with the latter one having priority.
        Will be empty if nothing is found.
    """
    if not paths_to_check:
        paths_to_check = [
            r"C:\Program Files\Bitplane\ImarisFileConverter ",
            r"C:\Program Files\Bitplane\Imaris ",
        ]

    imaris_paths = [""]

    for check in paths_to_check:
        hits = glob.glob(check + "*")
        imaris_paths += sorted(
            hits, key=lambda x: float(x.replace(check, "").replace(".", ""))
        )

    return imaris_paths[-1]

# ─── MAIN CODE ──────────────────────────────────────────────────────────────────

# get start time
execution_start_time = time.time()

first_czi = str(input_path).replace("\\", "/")
project_path = first_czi.replace(".czi",".xml")
fused_path = first_czi.replace(".czi","_fused.xml")
filename = os.path.basename(first_czi)
project_filename = filename.replace(".czi",".xml")
parent_dir = os.path.dirname(first_czi)

# define dataset
if reader == "LightSheet 7 (Zen tiling)":
    IJ.run(
        "Define Multi-View Dataset",
        "define_dataset=[Zeiss Lightsheet 7 Dataset Loader (Bioformats)] " +
        "project_filename=[" + project_filename + "] " +
        "first_czi=[" + first_czi + "] " +
        "apply_rotation_to_dataset " +
        "fix_bioformats"
    )

elif reader == "LightSheet Z.1 / 7 (Tile scan macro)":
    IJ.run(
        "Define Multi-View Dataset",
        "define_dataset=[Zeiss Lightsheet Z.1 Dataset Loader (Bioformats)] " +
        "project_filename=[" + project_filename + "] " +
        "first_czi=[" + first_czi + "] " +
        "apply_rotation_to_dataset " +
        "fix_bioformats"
    )

# resave as h5/xml
IJ.run(
    "As HDF5",
    "select=[" + project_path + "] " +
    "resave_angle=[All angles] " +
    "resave_channel=[All channels] " +
    "resave_illumination=[All illuminations] " +
    "resave_tile=[All tiles] " +
    "resave_timepoint=[All Timepoints] " +
    "use_deflate_compression " +
    "export_path=[" + project_path + "]"
)

# detect interest point with advanced settings
# TODO: maybe limit to only one channel, then forward the detections to all other channels
# TODO: add option [Interactive ...], the skip the automatic values...if interactive mode is possible during a script.
# TODO: make sigma and threshold user variables, but set the defaults to 1.8 and 0.008
# TODO: test GPU integration
IJ.run(
    "Detect Interest Points for Registration",
    "select=[" + project_path + "] " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "type_of_interest_point_detection=Difference-of-Gaussian " +
    "label_interest_points=beads " +
    "limit_amount_of_detections " +
    "group_tiles group_illuminations " +
    "subpixel_localization=[3-dimensional quadratic fit] " +
    "interest_point_specification=[Advanced ...] " +
    "downsample_xy=[Match Z Resolution (less downsampling)] " +
    "downsample_z=1x " +
    "sigma=1.80000 " +
    "threshold=0.00800 " +
    "find_maxima " +
    "maximum_number=3000 " +
    "type_of_detections_to_use=Brightest " +
    "compute_on=[CPU (Java)]"
)

# register using interest points
IJ.run(
    "Register Dataset based on Interest Points",
    "select=[" + project_path + "] " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "registration_algorithm=[Precise descriptor-based (translation invariant)] " +
    "registration_in_between_views=[Compare all views against each other] " +
    "interest_points=beads " +
    "group_tiles " +
    "group_illuminations " +
    "group_channels " +
    "fix_views=[Fix first view] " +
    "map_back_views=[Do not map back (use this if views are fixed)] " +
    "transformation=Affine " +
    "regularize_model " +
    "model_to_regularize_with=Rigid " +
    "lamba=0.10 " +
    "number_of_neighbors=3 " +
    "redundancy=3 " +
    "significance=2 " +
    "allowed_error_for_ransac=5 " +
    "ransac_iterations=Normal " +
    "interestpoint_grouping=[Group interest points (simply combine all in one virtual view)] " +
    "interest=5"
)

# select illuminations
if autoselect_illuminations:
    IJ.run(
        "Select Illuminations",
        "select=[" + project_path + "] " +
        "selection=[Pick brightest]"
    )

# TODO: introduce option for auto bounding box function

# fuse and save as hdf5
if fuse:
    # check the file size of the file to be fused and compare to the available RAM
    stitched_filesize = os.path.getsize( project_path.replace(".xml",".h5") )
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
    shutil.copy2(project_path, temp)
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
        "export_path=["+ fused_path + "]"
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

imaris_path = locate_latest_imaris()

if fuse and convert_to_ims and imaris_path:
    IJ.log("converting to Imaris5 format...")

    first_fused_tif = temp + "/fused_tp_0_ch_0.tif"
    os.chdir(locate_latest_imaris())
    command = 'ImarisConvert.exe -i "%s" -of Imaris5 -o "%s" -fsdc _CH_ -fsdt _TP_' % (
        first_fused_tif,
        first_czi.replace(".czi", ".ims"),
    )
    # print("\n%s" % command)
    IJ.log("Converting to Imaris5 .ims...")
    subprocess.call(command, shell=True)
    IJ.log("Conversion to .ims is finished")


if not imaris_path:
    print("Can't find Imaris path, conversion will be skipped")

total_execution_time_min = round( (time.time() - execution_start_time) / 60.0 )

if email_address:
    send_mail( "imcf@unibas.ch", email_address, filename, total_execution_time_min )
else:
    print("Email address field is empty, no email was sent")

IJ.log("\n~~~ Job summary ~~~")
IJ.log("Filename: " + str( filename ))
IJ.log("Automatically select best illumination side: " + str( autoselect_illuminations ))
IJ.log("Fuse image: " + str( fuse ))
IJ.log("Downsample fused image: " + str( downsampling ))
IJ.log("Convert fused image to Imaris5: " + str( convert_to_ims ))
IJ.log("Send info email to: " + str( email_address ))
IJ.log("Total time in minutes: " + str( total_execution_time_min ))
IJ.log("All done")
IJ.selectWindow("Log")
IJ.saveAs("Text", str(first_czi).replace(".czi", "") + "_MultiviewReconstruction_Log")
