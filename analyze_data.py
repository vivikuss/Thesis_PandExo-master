import numpy as np
import matplotlib.pyplot as plt
import pandexo.engine.justplotit as jpi
import pickle
from matplotlib import ticker

### ADJUST THIS PART ###
# Paths
pic = '/Users/new/Desktop/THESIS/THESIS_picaso-master'

### K2-18b
#input_pandexo = ['pandexo_k218b_spectrum1.txt','pandexo_k218b_spectrum2.txt','pandexo_k218b_spectrum3.txt']
#input_picaso = [pic + '/spectrum_k218b_case1.txt',pic + '/spectrum_k218b_case2.txt', pic + '/spectrum_k218b_case3.txt']  
#title = 'pandexoplot_combined_k218b_he.png' # 'pandexoplot_combined_k218b_he_h2.png'

### LHS 1140b
input_pandexo = ['pandexo_lhs_spectrum1.txt','pandexo_lhs_spectrum2.txt','pandexo_lhs_spectrum3.txt']
input_picaso = [pic + '/spectrum_lhs_case1.txt',pic + '/spectrum_lhs_case2.txt', pic + '/spectrum_lhs_case3.txt']  
title = 'pandexoplot_combined_lhs_he_h2.png' # 'pandexoplot_combined_lhs_he.png' #

#labels = ['97.4% He, 0.8% CO2','47.4% He, 50.8% CO2','5% He, 95% CO2', '97.4% H2, 0.8% CO2']
only_he = False         # Plot 97.4% He vs 47.4% He if True, plot 97.4% He vs 97.4% H2 if False
###

picaso_labels = ['Full Spectrum (PICASO)','Full Spectrum (PICASO)']
reconstructed_labels = ['Reconstructed Spectrum', 'Reconstructed Spectrum']
simulated_labels = ['Simulated Data Point','Simulated Data Point']

fig, axs = plt.subplots(2, 2, figsize=(12, 6), sharex='col', sharey=True)
formatter = ticker.ScalarFormatter(useMathText=True)
formatter.set_scientific(True)
formatter.set_powerlimits((-1, 1))
plt.rcParams.update({'font.size': 13})

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
plt.savefig(title, dpi=500)
plt.show()


