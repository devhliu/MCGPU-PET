import numpy as np
import nibabel as nib
import os
import subprocess

def create_dummy_nifti():
    data = np.zeros((3, 3, 3), dtype=np.int32)
    data[1, 1, 1] = 2 # Water
    data[0, 0, 0] = 1 # Air
    
    img = nib.Nifti1Image(data, np.eye(4)) # Identity affine, 1mm spacing? No, default is 1mm usually.
    # Set spacing to 2mm to test conversion
    header = img.header
    header.set_zooms((2.0, 2.0, 2.0))
    
    nib.save(img, 'test_mat.nii.gz')
    print("Created test_mat.nii.gz")

if __name__ == "__main__":
    create_dummy_nifti()
    
    # Run conversion
    cmd = [
        "python3", "nifti2vox.py",
        "-m", "test_mat.nii.gz",
        "-o", "test_out.vox"
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    
    # Check output
    if os.path.exists("test_out.vox"):
        print("Output file created.")
        with open("test_out.vox", 'r') as f:
            print(f.read())
    else:
        print("Output file failed.")
