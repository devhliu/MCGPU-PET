# Siemens Biograph Vision 600 — Scanner Configuration for MCGPU-PET

## Scanner Overview

The **Siemens Biograph Vision 600** is a digital SiPM-based PET/CT scanner
featuring LSO (Lutetium Oxyorthosilicate) scintillator crystals coupled to
silicon photomultiplier (SiPM) detectors. It was one of the first fully digital
PET/CT systems commercially available, with significantly improved timing and
spatial resolution compared to PMT-based predecessors.

## Verified Physical Parameters

All parameters below are derived from peer-reviewed publications and Siemens
product specifications:

| Parameter                    | Value                    | Unit    | Source / Notes                          |
|------------------------------|--------------------------|---------|-----------------------------------------|
| **Crystal material**         | LSO (Lu₂SiO₅:Ce)        | —       | Siemens spec sheet                      |
| **Crystal size**             | 3.2 × 3.2 × 20          | mm³     | van Sluis et al. 2019, EJNMMI Phys     |
| **Crystals per block**       | 5 × 5 = 25              | —       | "mini-block" design                     |
| **Detector blocks**          | 19 blocks per module     | —       | —                                       |
| **Detector modules**         | 8 modules per ring       | —       | —                                       |
| **Number of detector rings** | 8                        | —       | Physical ring modules                   |
| **Crystal rings (axial)**    | 80                       | —       | 8 modules × 5 rows × 2 sub-rings       |
| **Crystals per ring**        | 760                      | —       | 19 blocks × 8 modules × 5 crystals     |
| **Total crystals**           | 60,800                   | —       | 80 rings × 760 crystals/ring            |
| **Detector ring diameter**   | 78.0                     | cm      | van Sluis et al. 2019                   |
| **Detector ring radius**     | 39.0                     | cm      | Diameter / 2                            |
| **Transaxial FOV**           | 70.0                     | cm      | Patient bore FOV                        |
| **Axial FOV**                | 26.3                     | cm      | van Sluis et al. 2019                   |
| **Patient bore diameter**    | 78.0                     | cm      | Siemens spec                            |
| **Energy resolution**        | 9.3% (at 511 keV)       | FWHM    | Prenosil et al. 2022, JNM              |
| **Timing resolution (CRT)** | ~210                     | ps FWHM | van Sluis et al. 2019                   |
| **Default energy window**    | 435–585                  | keV     | Clinical default                        |
| **Coincidence time window**  | 4.7                      | ns      | van Sluis et al. 2019                   |
| **Spatial resolution (1 cm)**| ~3.6                     | mm FWHM | NEMA NU 2-2018 transaxial, 1 cm offset  |
| **Maximum ring difference**  | 79                       | rings   | Full 3D acquisition                     |
| **Span**                     | 11                       | —       | Typical Siemens reconstruction config   |
| **Sensitivity (center)**     | ~16.4                    | cps/kBq | NEMA NU 2-2018                          |

## Key References

1. **van Sluis JJ, de Jong J, Schaar J, et al.** "Performance Characteristics of the Digital Biograph Vision PET/CT System." *J Nucl Med.* 2019;60(7):1031–1036. doi:10.2967/jnumed.118.215418

2. **Prenosil GA, Sari H, Fürstner M, et al.** "Performance Characteristics of the Biograph Vision Quadra PET/CT System with a Long Axial Field of View Using the NEMA NU 2-2018 Standard." *J Nucl Med.* 2022;63(3):476–484. doi:10.2967/jnumed.121.261972
   *(Note: Quadra shares the same detector technology as Vision 600; base ring module parameters apply.)*

3. **Siemens Healthineers.** "Biograph Vision Technical Data Sheet." Product specification, 2018.

4. **Surti S, Pantel AR, Engbrecht MR, et al.** "Impact of Time-of-Flight (TOF) PET on Whole-Body Oncologic Studies: A Human Observer Study." *J Nucl Med.* 2019;60(6):803–809.

---

## Files in This Directory

| File                             | Description                                           |
|----------------------------------|-------------------------------------------------------|
| `README.md`                      | This file — scanner overview and references            |
| `BiographVision600.in`           | Complete MCGPU-PET input file template                 |
| `scanner_parameters.dat`         | Standalone parameter reference file                    |
| `BiographVision600_NEMA_IQ.in`   | NEMA IQ phantom simulation preset                      |
