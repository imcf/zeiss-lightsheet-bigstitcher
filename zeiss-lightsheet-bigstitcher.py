# ─── SCRIPT PARAMETERS ──────────────────────────────────────────────────────────

#@ File (label="Select first CZI file", description="select only the first czi file")  input_path
#@ String (label="What reader to use ?", choices={"LightSheet 7 (Zen tiling)","LightSheet Z.1 / 7 (Tile scan macro)"}, style="listBox") reader
#@ Boolean (label="Automatically select best illumination side", description="discard the other illumination", value=false) autoselect_illuminations
#@ Boolean (label="Fuse image", description="save dataset as fused xml/tiff images or as h5/xml if size is too large", value=true) fuse
#@ Boolean (label="Convert fused image to Imaris5", description="convert to fused image to *.ims", value=true) convert_to_ims
#@ Boolean (label="Delete intermediate files", description="keep only final fused image", value=true) delete_temp_files
#@ String (label="Send info email to: ", description="empty = skip") email_address

# TODO: include tp range request by default, maybe in two variables, t_start and t_end. Then use them instead of "[All Timepoints]"

# ─── IMPORTS ────────────────────────────────────────────────────────────────────

# python imports
import os
import glob
import time
import smtplib
import shutil
import subprocess
import sys

# Imagej imports
from ij import IJ
from ij.gui import YesNoCancelDialog

# ome imports to parse metadata
from loci.formats import ImageReader
from loci.formats import MetadataTools

from javax.xml.parsers import DocumentBuilder
from javax.xml.parsers import DocumentBuilderFactory

import org.w3c.dom.Document
import org.w3c.dom.Element
import org.w3c.dom.Node
import org.w3c.dom.NodeList

from loci.formats.in import ZeissCZIReader, DynamicMetadataOptions, MetadataOptions
from loci.formats import ImageReader, TileStitcher
from loci.formats import MetadataTools

# requirements:
# BigStitcher, Multiview Reconstruction >= 10.2
# Laurent Guerards update of multiview-reconstruction.jar

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


def send_mail(sender, recipient, filename, total_execution_time_min):
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

    header = "From: imcf@unibas.ch\n"
    header += "To: %s\n"
    header += "Subject: Your Lightsheet processing job finished successfully\n\n"
    text = (
        "Dear recipient,\n\n"
        "This is an automated message from the Zeiss Lightsheet BigStitcher.\n"
        "Your file %s has been successfully processed (%s min).\n\n"
        "Kind regards,\n"
        "The IMCF-team"
    )

    message = header + text

    try:
        smtpObj = smtplib.SMTP("smtp.unibas.ch")
        smtpObj.sendmail(
            sender, recipient, message % (recipient, filename, total_execution_time_min)
        )
        print("Successfully sent email")
    except smtplib.SMTPException:
        print("Error: unable to send email")


def get_calibration_from_metadata(path_to_image):
    """get the pixel calibration from a given image using Bio-Formats

    Parameters
    ----------
    path_to_image : str
        full path to the input image

    Returns
    -------
    array
        the physical px size as float for x,y,z
    """
    reader = ImageReader()
    omeMeta = MetadataTools.createOMEXMLMetadata()
    reader.setMetadataStore(omeMeta)
    reader.setId(str(path_to_image))

    physSizeX = omeMeta.getPixelsPhysicalSizeX(0)
    physSizeY = omeMeta.getPixelsPhysicalSizeY(0)
    physSizeZ = omeMeta.getPixelsPhysicalSizeZ(0)
    image_calibration = [physSizeX.value(), physSizeY.value(), physSizeZ.value()]
    reader.close()

    return image_calibration


def check_fusion_settings(czi_path):
    """Check for fusion settings and asks confirmation to user if H5/XML fusion

    Parameters
    ----------
    czi_path : str
        Path to the CZI file

    Returns
    -------
    bool
        Bool for fusion
    str
        Method of RAM handling
    bool
        Bool for TIFF or H5/XML fusion
    """

    # Default values
    do_fusion = True
    fuse_tiff = True

    reader = ZeissCZIReader()
    m = DynamicMetadataOptions()
    m.setBoolean(ZeissCZIReader.ALLOW_AUTOSTITCHING_KEY, False)
    m.setBoolean(ZeissCZIReader.RELATIVE_POSITIONS_KEY, True)
    reader.setMetadataOptions(m)
    omeMeta = MetadataTools.createOMEXMLMetadata()
    reader.setMetadataStore(omeMeta)
    reader.setId(str(czi_path))

    nbr_tp = omeMeta.getTimestampAnnotationCount() + 1
    nbr_chnl = omeMeta.getChannelCount(0)

    # check the file size of the file to be fused and compare to the available RAM
    # h5_filesize = os.path.getsize(export_path_temp + ".h5")
    h5_filesize = os.path.getsize(czi_path) / 2
    free_memory = get_free_memory()

    print("h5 filesize " + convert_bytes(h5_filesize))
    print("free memory in ij " + convert_bytes(free_memory))

    # TODO: include in below calculation t_end, since only one t is fused at a time.
    if free_memory > (6 * h5_filesize / downsampling):
        ram_handling = "[Precompute Image]"
    else:
        ram_handling = "Virtual"
    print("fusion mode used " + str(ram_handling))

    # if autoselect_illuminations and nbr_ill > 1:
    #     ill_value = 2
    # else:
    #     ill_value = 1

    ram_requirement = 2 * h5_filesize / (nbr_tp * nbr_chnl * downsampling)
    print(ram_requirement)
    sufficient_ram = ram_requirement < free_memory / 10

    if not sufficient_ram:
        try:
            yn = YesNoCancelDialog(
                IJ.getInstance(),
                "Warning!",
                (
                    "File size is too big to use TIFF for fusion\n"
                    "Fusion will happen using H5/XML which might take weeks. Are you "
                    "sure you want to do fusion ?\n"
                    "All steps prior to fusion would still happen, allowing for manual "
                    "fusion and tile selection."
                ),
            )
            if yn.yesPressed():
                fuse_tiff = False
            else:
                do_fusion = False
        except Exception:
            # when running headless the above will raise a java.awt.HeadlessException,
            # so we simply fall back to the same behavior as if "No" was clicked:
            do_fusion = False
    return do_fusion, ram_handling, fuse_tiff


def convert_bytes(size):
    """Convert size from bytes to a readable value

    Parameters
    ----------
    size : int
        Byte size

    Returns
    -------
    str
        Easy to read value with the correct unit
    """
    for x in ["bytes", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return "%3.1f %s" % (size, x)
        size /= 1024.0

    return size


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

execution_start_time = time.time()
downsampling = 1
# downsampling is not a user variable anymore, I think they all use 1.
# with the new LS7 tiling, Zen can open the tiled raw data for a sneak peak as well.
# Also, calculating the correct px size fo the downsampled fused image seems non trivial as well.

# get filename and path names
input_path = str(input_path)
first_czi = input_path.replace("\\", "/")
filename = os.path.basename(input_path)
parent_dir = os.path.dirname(input_path)
parent_dir = parent_dir.replace("\\", "/")
project_filename = filename.replace(".czi", ".xml")
project_filename_short = filename.replace(".czi", "")
project_path = parent_dir + "/" + project_filename

if fuse:
    fuse, ram_handling, fuse_tiff = check_fusion_settings(input_path)

# add a temp folder
temp = parent_dir + "/" + filename + "_temp"
if not os.path.exists(temp):
    os.mkdir(temp)

project_path_temp = temp + "/" + project_filename
export_path_temp = temp + "/" + project_filename_short
export_path_fused_temp = project_path_temp.replace(".xml", "_fused.xml")

# if no conversion is to ims is selected, save the fused tiff in a new folder next to the raw data instead
if not convert_to_ims:
    fused_tiff_dir = parent_dir + "/" + filename + "_fused"

    if not os.path.exists(fused_tiff_dir):
        os.mkdir(fused_tiff_dir)

    export_path_fused_temp = (
        fused_tiff_dir + "/" + project_filename.replace(".xml", "_fused.xml")
    )

# IJ.log("retrieving calibration from " + str(filename) + ", this can take ~5 minutes..." )
# first_czi_calibration = get_calibration_from_metadata(first_czi)
# get_cal_time = round( (time.time() - execution_start_time) / 60.0 )
# print("time to get calibration [min]" + str(get_cal_time))

# run BigStitcher
# define_dataset

if reader == "LightSheet 7 (Zen tiling)":
    IJ.run(
        "Define dataset ...",
        "define_dataset=[Zeiss Lightsheet 7 Dataset Loader (Bioformats)] "
        + "project_filename=["
        + project_filename
        + "] "
        + "first_czi=["
        + first_czi
        + "] "
        + "apply_rotation_to_dataset "
        + "fix_bioformats",
    )
elif reader == "LightSheet Z.1 / 7 (Tile scan macro)":
    IJ.run(
        "Define dataset ...",
        "define_dataset=[Zeiss Lightsheet Z.1 Dataset Loader (Bioformats)] "
        + "project_filename=["
        + project_filename
        + "] "
        + "first_czi=["
        + first_czi
        + "] "
        + "apply_rotation_to_dataset "
        + "fix_bioformats",
    )

dataset_def_time = round((time.time() - execution_start_time) / 60.0)
print("time to define dataset [min]" + str(dataset_def_time))

xml_file = project_path

dbf = DocumentBuilderFactory.newInstance()
db = dbf.newDocumentBuilder()
dom = db.parse(xml_file)
experimentEL = dom.getDocumentElement()

nodeList = dom.getElementsByTagName("Attributes")
for i in range(nodeList.getLength()):
    node = nodeList.item(i).getAttributes().getNamedItem("name").getNodeValue()
    if node == "channel":
        nbr_chnl = int(nodeList.item(i).getElementsByTagName("Channel").getLength())
    if node == "illumination":
        nbr_ill = int(nodeList.item(i).getElementsByTagName("Illumination").getLength())

timepoints_node = dom.getElementsByTagName("Timepoints")
nbr_tp = (
    int(timepoints_node.item(0).getElementsByTagName("last").item(0).getTextContent())
    + 1
)

IJ.log(
    "Found "
    + str(nbr_chnl)
    + " channels, "
    + str(nbr_ill)
    + " illuminations and "
    + str(nbr_tp)
    + " timepoints"
)

shutil.copy2(project_path, project_path_temp)
shutil.copy2(project_path, export_path_fused_temp)

if not convert_to_ims:
    shutil.copy2(project_path, export_path_fused_temp)

# resave as h5/xml
IJ.run(
    "As HDF5 ...",
    "select=["
    + project_path
    + "] "
    + "resave_angle=[All angles] "
    + "resave_channel=[All channels] "
    + "resave_illumination=[All illuminations] "
    + "resave_tile=[All tiles] "
    + "resave_timepoint=[All Timepoints] "
    + "export_path=["
    + project_path_temp
    + "]",
)

resave_time = round((time.time() - execution_start_time) / 60.0) - dataset_def_time
print("time to resave dataset to h5/xml [min]" + str(resave_time))

# calculate pairwise shifts
IJ.run(
    "Calculate pairwise shifts ...",
    "select=["
    + project_path_temp
    + "] "
    + "process_angle=[All angles] "
    + "process_channel=[All channels] "
    + "process_illumination=[All illuminations] "
    + "process_tile=[All tiles] "
    + "process_timepoint=[All Timepoints] "
    + "method=[Phase Correlation] "
    + "channels=[Average Channels] "
    + "illuminations=[Average Illuminations]",
)

# filter shifts with 0.7 corr. threshold
IJ.run(
    "Filter pairwise shifts ...",
    "select=["
    + project_path_temp
    + "] "
    + "filter_by_link_quality "
    + "min_r=0.7 "
    + "max_r=1 "
    + "max_shift_in_x=0 "
    + "max_shift_in_y=0 "
    + "max_shift_in_z=0 "
    + "max_displacement=0",
)

# do global optimization
IJ.run(
    "Optimize globally and apply shifts ...",
    "select=["
    + project_path_temp
    + "] "
    + "process_angle=[All angles] "
    + "process_channel=[All channels] "
    + "process_illumination=[All illuminations] "
    + "process_tile=[All tiles] "
    + "process_timepoint=[All Timepoints] "
    + "relative=2.500 "
    + "absolute=3.500 "
    + "global_optimization_strategy=[Two-Round using Metadata to align unconnected Tiles] "
    + "fix_group_0-0,",
)

# select illuminations
if autoselect_illuminations:
    IJ.run(
        "Select Illuminations",
        "select=[" + project_path_temp + "] " + "selection=[Pick brightest]",
    )

registration_time = round((time.time() - execution_start_time) / 60.0) - resave_time
print("time to register tiles [min]" + str(registration_time))

# TODO: introduce option for auto bounding box function

if fuse:

    if fuse_tiff:
        # re-save as tiff, as fusing *from* h5/xml is really slow
        IJ.run(
            "As TIFF ...",
            "select=["
            + project_path_temp
            + "] "
            + "resave_angle=[All angles] "
            + "resave_channel=[All channels] "
            + "resave_illumination=[All illuminations] "
            + "resave_tile=[All tiles] "
            + "resave_timepoint=[All Timepoints] "
            + "export_path=["
            + project_path_temp
            + "]",
        )

        # fuse dataset to a new xml/tiff, since fusing *to* h5/xml is really slow
        IJ.run(
            "Fuse dataset ...",
            "select=["
            + project_path_temp
            + "] "
            + "process_angle=[All angles] "
            + "process_channel=[All channels] "
            + "process_illumination=[All illuminations] "
            + "process_tile=[All tiles] "
            + "process_timepoint=[All Timepoints] "
            + "bounding_box=[Currently Selected Views] "
            + "downsampling="
            + str(downsampling)
            + " "
            + "pixel_type=[16-bit unsigned integer] "
            + "interpolation=[Linear Interpolation] "
            + "image="
            + ram_handling
            + " "
            + "interest_points_for_non_rigid=[-= Disable Non-Rigid =-] "
            + "blend "
            + "preserve_original "
            + "produce=[Each timepoint & channel] "
            + "fused_image=[Save as new XML Project (TIFF)] "
            + "export_path=["
            + export_path_fused_temp
            + "]",
        )
    else:
        IJ.log("Datasets too big, fusion will happen on the H5/XML")
        IJ.run(
            "Fuse dataset ...",
            "select=["
            + project_path_temp
            + "] "
            + "process_angle=[All angles] "
            + "process_channel=[All channels] "
            + "process_illumination=[All illuminations] "
            + "process_tile=[All tiles] "
            + "process_timepoint=[All Timepoints] "
            + "bounding_box=[Currently Selected Views] "
            + "downsampling="
            + str(downsampling)
            + " "
            + "pixel_type=[16-bit unsigned integer] "
            + "interpolation=[Linear Interpolation] "
            + "image="
            + ram_handling
            + " "
            + "interest_points_for_non_rigid=[-= Disable Non-Rigid =-] "
            + "blend "
            + "preserve_original "
            + "produce=[Each timepoint & channel] "
            + "fused_image=[Save as new XML Project (HDF5)] "
            + "export_path=["
            + export_path_fused_temp
            + "]",
        )

    fusion_time = round((time.time() - execution_start_time) / 60.0) - registration_time
    print("time to fuse dataset [min]" + str(fusion_time))

# free memory in IJ
IJ.log("collecting garbage...")
IJ.run("Collect Garbage", "")
time.sleep(60.0)
IJ.run("Collect Garbage", "")
time.sleep(60.0)
IJ.run("Collect Garbage", "")
time.sleep(60.0)

imaris_path = locate_latest_imaris()

# TODO: offer conversion to IMS or h5/xml or nothing, i.e leave as tiff
# convert to Imaris5 format
if fuse and convert_to_ims and imaris_path:
    if fuse_tiff:
        file_to_convert_to_ims = temp + "/fused_tp_0_ch_0.tif"
    else:
        print("i am here")
        file_to_convert_to_ims = export_path_fused_temp
    # imaris_voxelsize = "%s-%s-%s" % (first_czi_calibration[0], first_czi_calibration[1], first_czi_calibration[2])

    os.chdir(locate_latest_imaris())
    command = 'ImarisConvert.exe -i "%s" -of Imaris5 -o "%s" -fsdc _CH_ -fsdt _TP_' % (
        file_to_convert_to_ims,
        first_czi.replace(".czi", ".ims"),
    )
    print("\n%s" % command)
    IJ.log("Converting to Imaris5 .ims...")
    subprocess.call(command, shell=True)
    IJ.log("Conversion to .ims is finished")

    convert_to_ims_time = (
        round((time.time() - execution_start_time) / 60.0) - fusion_time
    )
    print("time to convert dataset to ims [min]" + str(convert_to_ims_time))

if not imaris_path:
    print("Can't find Imaris path, conversion will be skipped")

# remove temp folder
if delete_temp_files and fuse:
    shutil.rmtree(temp, ignore_errors=True)

total_execution_time_min = round((time.time() - execution_start_time) / 60.0)

if email_address:
    send_mail("imcf@unibas.ch", email_address, filename, total_execution_time_min)
else:
    print("Email address field is empty, no email was sent")

IJ.log("\n~~~ Job summary ~~~")
IJ.log("Filename: " + str(filename))
# IJ.log("First czi original voxel size xyz: " + str(first_czi_calibration) )
IJ.log("Automatically select best illumination side: " + str(autoselect_illuminations))
IJ.log("Fuse image: " + str(fuse))
if fuse == True:
    IJ.log("Fusion mode: " + str(ram_handling))
IJ.log("Convert fused image to Imaris5: " + str(convert_to_ims))
IJ.log("Delete intermediate files: " + str(delete_temp_files))
IJ.log("Send info email to: " + str(email_address))
IJ.log("Total time in minutes: " + str(total_execution_time_min))
IJ.log("All done")
IJ.selectWindow("Log")
IJ.saveAs("Text", str(first_czi) + "_BigStitcher_Log")
