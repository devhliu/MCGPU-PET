#!/usr/bin/env python3
import sys
import argparse
import numpy as np
import nibabel as nib

def convert_nifti_to_vox(material_nii, output_vox, density_nii=None, activity_nii=None):
    """
    Convert NIfTI files to MCGPU-PET .vox format.
    
    Args:
        material_nii (str): Path to material ID NIfTI file (integers 1..N).
        output_vox (str): Path to output .vox file.
        density_nii (str, optional): Path to density NIfTI file (g/cm^3).
        activity_nii (str, optional): Path to activity NIfTI file (Bq).
    """
    
    try:
        # Load Material Map
        print(f"Loading Material Map: {material_nii}")
        mat_img = nib.load(material_nii)
        # Force loading data as integer indices
        mat_data = np.asanyarray(mat_img.dataobj).astype(np.int32)
        
        # Squeeze singleton dimensions if 4D with time=1
        if mat_data.ndim == 4 and mat_data.shape[3] == 1:
            mat_data = mat_data.squeeze(axis=3)
            
        dims = mat_data.shape
        if len(dims) != 3:
            print(f"Error: Material NIfTI must be 3D. Got shape {dims}")
            sys.exit(1)
            
        nx, ny, nz = dims
        
        # Get voxel spacing in cm (NIfTI header units are usually mm, check 'xyzt_units' if needed, generally mm)
        # Default assumption: mm
        header = mat_img.header
        # zoom is pixdim[1:4]
        pixdim = header.get_zooms()[:3]
        dx, dy, dz = [p / 10.0 for p in pixdim]  # Convert mm to cm
        
        print(f"Volume Dimensions: {nx} x {ny} x {nz}")
        print(f"Voxel size (cm): {dx:.4f} x {dy:.4f} x {dz:.4f}")

        # Load Density Map
        if density_nii:
            print(f"Loading Density Map: {density_nii}")
            den_img = nib.load(density_nii)
            den_data = np.asanyarray(den_img.dataobj).astype(np.float32)
            if den_data.ndim == 4 and den_data.shape[3] == 1:
                den_data = den_data.squeeze(axis=3)
            if den_data.shape != dims:
                print(f"Error: Density map shape {den_data.shape} mismatch with Material map {dims}")
                sys.exit(1)
        else:
            print("No density map provided. Using default density 1.0 g/cm^3 for all voxels.")
            den_data = np.ones(dims, dtype=np.float32)

        # Load Activity Map
        if activity_nii:
            print(f"Loading Activity Map: {activity_nii}")
            act_img = nib.load(activity_nii)
            act_data = np.asanyarray(act_img.dataobj).astype(np.float32)
            if act_data.ndim == 4 and act_data.shape[3] == 1:
                act_data = act_data.squeeze(axis=3)
            if act_data.shape != dims:
                print(f"Error: Activity map shape {act_data.shape} mismatch with Material map {dims}")
                sys.exit(1)
        else:
            print("No activity map provided. Using default activity 0.0 Bq.")
            act_data = np.zeros(dims, dtype=np.float32)

        # Prepare output
        print(f"Writing to {output_vox}...")
        
        with open(output_vox, 'w') as f:
            # Header Section
            f.write("[SECTION VOXELS HEADER v.2008-04-13]\n")
            f.write(f"{nx} {ny} {nz} No. OF VOXELS IN X,Y,Z\n")
            f.write(f"{dx:.6f} {dy:.6f} {dz:.6f} VOXEL SIZE (cm) ALONG X,Y,Z\n")
            f.write(" 1                  COLUMN NUMBER WHERE MATERIAL ID IS LOCATED\n")
            f.write(" 2                  COLUMN NUMBER WHERE THE MASS DENSITY IS LOCATED\n")
            f.write(" 1                  BLANK LINES AT END OF X,Y-CYCLES (1=YES,0=NO)\n")
            f.write("[END OF VXH SECTION]\n")
            
            # Data Section. 
            # Loop order: Z (slowest), Y, X (fastest).
            # This corresponds to NIfTI's (x, y, z) data loaded as [x, y, z].
            # So we iterate z, then y, then x.
            
            for iz in range(nz):
                for iy in range(ny):
                    for ix in range(nx):
                        m_val = mat_data[ix, iy, iz]
                        d_val = den_data[ix, iy, iz]
                        a_val = act_data[ix, iy, iz]
                        # Material ID should be integer. 
                        # Density and Activity floats.
                        # Format: Material Density Activity
                        f.write(f"{m_val} {d_val:.6f} {a_val:.6e}\n")
                    # Blank line after X-cycle (end of a row)
                    f.write("\n")
                # Blank line after Y-cycle (end of a slice)? 
                # The "1 BLANK LINES AT END OF X,Y-CYCLES" suggests both X and Y cycles trigger a blank line.
                # If so, after a slice (end of Y-cycle), we get an extra blank line.
                f.write("\n")

        print("Conversion complete.")

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Convert NIfTI files to MCGPU-PET .vox format.")
    
    parser.add_argument("-m", "--material", required=True, 
                        help="Input Material ID NIfTI file (integers representing material indices)")
    
    parser.add_argument("-o", "--output", required=True, 
                        help="Output .vox file path")
                        
    parser.add_argument("-d", "--density", 
                        help="Input Density NIfTI file (g/cm^3). Optional. Default: 1.0 everywhere.")
                        
    parser.add_argument("-a", "--activity", 
                        help="Input Activity NIfTI file (Bq per voxel). Optional. Default: 0.0 everywhere.")

    args = parser.parse_args()
    
    convert_nifti_to_vox(args.material, args.output, args.density, args.activity)

if __name__ == "__main__":
    main()
