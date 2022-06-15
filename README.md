# Fiji scripts for processing Zeiss lightsheet Z.1/7 datasets using BigStitcher/ Multiview Reconstruction

These scripts are meant for automatic and easy "happy go lucky" processing of Zeiss Lightsheet datasets using the amazing [BigStitcher](https://imagej.net/BigStitcher) and [MultiView Reconstruction](https://imagej.net/Multiview-Reconstruction) in Fiji.

The goal is to provide a simple user interface to reduce the barrier of using the Lightsheet system for everyday users, for example in a facility environment. 
The scripts set default parameters that worked for several different usecases.

## Requirements
forked multiview-reconstruction-0.11.4-SNAPSHOT.jar which includes a Zeiss Lightsheet 7 reader (props to @lguerard)
https://github.com/imcf/multiview-reconstruction/releases/tag/0.11.4

If you would like to use the "convert to Imaris" function, 
- Imaris (Windows)

If you would like to use the mailing function,
- please change the smtp server settings according to your institute


## zeiss-lightsheet-bigstitcher
For stitching tiled datasets.

## zeiss-lightsheet-multiview-reconstruction.py
For reconstructing MultiView (=multi-angle) datasets
