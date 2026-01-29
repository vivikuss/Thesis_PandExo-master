

import numpy as np

# Monkey-patch: add 'bool' to numpy if missing
if not hasattr(np, 'bool8'):
    np.bool8 = bool

import re
from pathlib import Path
import matplotlib.pyplot as plt
import pandexo.engine.justplotit as jpi
import pickle
from matplotlib import ticker

### ADJUST THIS PART ###
# Paths
user = f"/Users/new/Desktop/"     #### CUSTOMIZE ####
pic = user + 'THESIS_picaso-master-main'

### K2-18b
#input_pandexo = ['pandexo_k218b_spectrum1.txt','pandexo_k218b_spectrum2.txt','pandexo_k218b_spectrum3.txt']
#input_picaso = [pic + '/spectrum_k218b_case1.txt',pic + '/spectrum_k218b_case2.txt', pic + '/spectrum_k218b_case3.txt']  
#title = 'pandexoplot_combined_k218b_he.png' # 'pandexoplot_combined_k218b_he_h2.png'

### LHS 1140 b
input_pandexo = ['pandexo_lhs_spectrum3.txt','pandexo_lhs_spectrum1.txt','pandexo_lhs_spectrum2.txt']
input_picaso = [pic + '/spectrum_lhs_case3.txt',pic + '/spectrum_lhs_case1.txt', pic + '/spectrum_lhs_case2.txt']  
title = 'pandexoplot_combined_lhs_h2_he_n2_lime.png' #'pandexoplot_combined_lhs_he_h2.png' # 'pandexoplot_combined_lhs_he.png' #

# Read raw RTF text
rtf_path = Path("Damiano_JWST.rtf") 
text = rtf_path.read_text(errors="ignore")

# wavelength_start-wavelength_end   ppm   error
row_pattern = re.compile(r"(\d+\.\d+)\s*-\s*(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)")
mu, ppm, err = [], [], []

for match in row_pattern.finditer(text):
    w_lo, w_hi, val, sigma = map(float, match.groups())
    mu.append(0.5 * (w_lo + w_hi))  # bin center
    ppm.append(val)
    err.append(sigma)

mu = np.array(mu)
ppm = np.array(ppm)*1e-6
err = np.array(err)*1e-6

sorted_indices = np.argsort(mu)
mu = mu[sorted_indices]
ppm = ppm[sorted_indices]
err = err[sorted_indices]

print(f"Damiano data imported")

### radii ###                               # Damiano et al 2024
Rp = 0.1543                         # Rjup
Rstar = 2.0435                          # Rjup

#labels = ['97.4% He, 0.8% CO2','47.4% He, 50.8% CO2','5% He, 95% CO2', '97.4% H2, 0.8% CO2']
only_he = False         # Plot 97.4% He vs 47.4% He if True, plot 97.4% He vs 97.4% H2 if False
plot_all = True         # Plot 99% He vs 99% N2 vs. 99% H2
###

picaso_labels = ['Full Spectrum (PICASO)','Full Spectrum (PICASO)']
reconstructed_labels = ['Reconstructed Spectrum', 'Reconstructed Spectrum']
simulated_labels = ['Simulated Data Point','Simulated Data Point']

formatter = ticker.ScalarFormatter(useMathText=True)
formatter.set_scientific(True)
formatter.set_powerlimits((-1, 1))
plt.rcParams.update({'font.size': 13})

if(not plot_all):
    fig, axs = plt.subplots(2, 2, figsize=(12, 6), sharex='col', sharey=True)

    for k, (pan, pica) in enumerate(zip(input_pandexo,input_picaso)):
        j = k
        if(only_he and k == 2): continue
        if(not only_he):
            if k == 1: continue
            if k == 2: j = 1
        i = k + 1

        # Load PandExo
        data = np.loadtxt(pan, skiprows=1)
        pandexo_data = np.array(data)
        pandexo_wave = pandexo_data[:,0]
        pandexo_spec_fin = pandexo_data[:,1]
        pandexo_trans = pandexo_data[:,2]
        pandexo_errors = pandexo_data[:,3]

        # Load PICASO
        data = np.loadtxt(pica, skiprows=0)
        picaso_data = np.array(data)
        picaso_wave = picaso_data[:,0]
        picaso_trans = picaso_data[:,1]

        row, col = 0, j  # top row
        ax1 = axs[row][col]
        row, col = 1, j  # bottom row
        ax2 = axs[row][col]

        if(k==0):
            ax1.plot(picaso_wave, picaso_trans, color='black', linewidth=1.0, label='Full Spectrum (PICASO)')
            ax2.plot(pandexo_wave, pandexo_spec_fin, color='dodgerblue', linewidth=2.0, label='Reconstructed Spectrum')
            ax2.errorbar(pandexo_wave, pandexo_trans, yerr=pandexo_errors, fmt='.', color='darkred', 
                        markersize=2.5, linewidth=0.9, label='Simulated Data Point')
        if(k==1):
            ax1.plot(picaso_wave, picaso_trans, color='black', linewidth=1.0, label='Full Spectrum (PICASO)')
            ax2.plot(pandexo_wave, pandexo_spec_fin, color='dodgerblue', linewidth=2.0, label='Reconstructed Spectrum')
            ax2.errorbar(pandexo_wave, pandexo_trans, yerr=pandexo_errors, fmt='.', color='darkred', 
                        markersize=2.5, linewidth=0.9, label='Simulated Data Point')
            
        if(k==2):
            ax1.plot(picaso_wave, picaso_trans, color='black', linewidth=1.0, label='Full Spectrum (PICASO)')
            ax2.plot(pandexo_wave, pandexo_spec_fin, color='dodgerblue', linewidth=2.0, label='Reconstructed Spectrum')
            ax2.errorbar(pandexo_wave, pandexo_trans, yerr=pandexo_errors, fmt='.', color='darkred', 
                        markersize=2.5, linewidth=0.9, label='Simulated Data Point')

        ax1.yaxis.set_major_formatter(formatter)
        ax2.yaxis.set_major_formatter(formatter)
        ax1.grid(True)
        ax2.grid(True)
        ax2.set_xlim([0.6, 5.0])
        ax2.set_ylim([0.53e-2, 0.63e-2])

    # Label outer axes
    axs[1,0].set_xlabel(r'Wavelength ($\mu$m)', fontsize=13)
    axs[1,1].set_xlabel(r'Wavelength ($\mu$m)',fontsize=13)
    axs[0,0].set_ylabel(r'Transit Depth $R_p^2/R_*^2$',fontsize=13)
    axs[1,0].set_ylabel(r'Transit Depth $R_p^2/R_*^2$',fontsize=13)

    axs[0,0].legend(loc='best')
    axs[1,0].legend(loc='best')
    axs[0,1].legend(loc='best')
    axs[1,1].legend(loc='best')

    fig.tight_layout()
    #plt.savefig(title, dpi=500)
    plt.show()

if(plot_all):
    labels = [r'H$_2$', r"He", r'N$_2$']
    #data_colors = ['darkred', 'darkslategrey', 'olive']
    data_colors = ['coral','darkviolet','dodgerblue']
    recon_colors = ['tomato', 'indigo', 'dodgerblue']
    fig, (ax1, ax2) = plt.subplots(2,1, figsize=(12, 8), sharey = True, sharex = True)
    for j, (pan, pica, lab, dat_colo, recon_colo) in enumerate(zip(input_pandexo,input_picaso,labels,data_colors,recon_colors)):
    
        # Load PandExo
        data = np.loadtxt(pan, skiprows=1)
        pandexo_data = np.array(data)
        pandexo_wave = pandexo_data[:,0]
        pandexo_spec_fin = pandexo_data[:,1]
        pandexo_trans = pandexo_data[:,2]
        pandexo_errors = pandexo_data[:,3]

        # Load PICASO
        data = np.loadtxt(pica, skiprows=0)
        picaso_data = np.array(data)
        picaso_wave = picaso_data[:,0]
        picaso_trans = picaso_data[:,1]

        ax1.plot(picaso_wave, picaso_trans, color=dat_colo, linestyle='dashed',linewidth=0.8,label=lab)
        ax2.errorbar(pandexo_wave, pandexo_trans, yerr=pandexo_errors, fmt='.', color=dat_colo, 
                    markersize=2.5, linewidth=0.9, label=lab)
        ax2.plot(pandexo_wave, pandexo_spec_fin, color=recon_colo, linewidth=2.0)
    
        ax1.yaxis.set_major_formatter(formatter)
        ax2.yaxis.set_major_formatter(formatter)
        ax1.grid(True)
        ax2.grid(True)
        ax2.set_xlim([0.6, 5.0])
        ax2.set_ylim([0.53e-2, 0.63e-2])

    ax1.set_title(r'Full Spectrum (PICASO)')
    ax2.set_title(r'Reconstructed Spectra (thick line) from simulated Data Points')
    ax1.set_xlabel(r'Wavelength ($\mu$m)', fontsize=13)
    ax2.set_xlabel(r'Wavelength ($\mu$m)',fontsize=13)
    ax1.set_ylabel(r'Transit Depth $R_p^2/R_*^2$',fontsize=13)
    ax2.set_ylabel(r'Transit Depth $R_p^2/R_*^2$',fontsize=13)

    #overplot Damiano data
    pandexo_min = np.min(pandexo_spec_fin)
    ppm_min = np.min(ppm)
    flat_spectrum = Rp**2/Rstar**2
    ppm += flat_spectrum - ppm_min

    #ax2.plot(mu, ppm, color="black", linewidth=2.0)
    ax2.errorbar(mu, ppm, yerr=err, fmt = ".", ecolor="black", linewidth=3.0, capsize=2.5)
    ax2.errorbar(mu, ppm, yerr=err, fmt = "D", color="lime", markersize=4.5, markeredgecolor = "black", linewidth=1.5, label="Observation")

    ax1.legend(loc='best')
    ax2.legend(loc='upper left')

    fig.tight_layout()
    plt.savefig(title, dpi=500)
    plt.show()
