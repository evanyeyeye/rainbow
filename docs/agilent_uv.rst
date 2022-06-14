.. _agilentuv:

==========================
Agilent UV Data (.ch, .uv)
==========================

Agilent UV data is stored in .ch and .uv binary files. 

The .ch files contain data for a single wavelength after a user-specified bandwidth,reference wavelength, and reference bandwith has been applied (to correct for drift). We do not currently know the calculation formula. 

The .uv files contain raw data collected across a larger spectrum. 

The .ch files are usually more interesting for the user, so we describe their file structure first. More information about .uv files can be found in the following section. 

Agilent .ch File Structure (UV)
===============================

Note that this section pertains only to the .ch files that contain UV data, which are not the same as the .ch files that contain FID data. 

These .ch files are comprised of a file header and data body. 

File header
-----------

The file header is 0x1800 (6144) bytes long and contains readable strings and unreadable data values. These strings and data values have fixed offsets in all files of this type. 

Agilent .uv File Structure
==========================