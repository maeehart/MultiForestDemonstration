#!/usr/bin/env python
# coding: utf-8

# # Multiforest optimization notebook

# Above the code cells, there will be instructions how the users should modify the codes in the cells. If there are no instructions, then by default no changes should be needed for the cell.

# ## Define input output

# Define CC scenario data

# In[1]:


RCP = "RCP0" 
filename = "rslt_"+RCP+"_CentralFinland.zip"
sample = 1 # if sample = 1, the whole data is used


# Name definition for saved output, rule: _scenario_RCP_extension

# In[2]:


scenario = "MF"
extension = "100prc7FES" # some additional info to the saved output


## Read .py class

module_path = os.path.abspath(os.path.join('..'))
if module_path not in sys.path:
    sys.path.append(module_path+"/py_class")

import multiFunctionalOptimization as MFO

from importlib import reload
reload(MFO)

mfo = MFO.MultiFunctionalOptimization(solver='CPLEX')

import wget
import os
import pandas as pd
import numpy as np


## Read data

mfo.readData(filename,
             # If no sample ratio given, the ratio is assumed to be 1
             sampleRatio= sample
             # Sample equally in all regions. 
             # Give the name of the column along the sampling should be equal (here region).             
             ,samplingSubsets = "region"
            )

## export list of id (important when only sample is used)

id = mfo.data.id

# https://www.freecodecamp.org/news/python-unique-list-how-to-get-all-the-unique-values-in-a-list-or-array/
def get_unique_numbers(numbers):

    list_of_unique_numbers = []

    unique_numbers = set(numbers)

    for number in unique_numbers:
        list_of_unique_numbers.append(number)

    return list_of_unique_numbers

id = get_unique_numbers(id)
id = pd.DataFrame(id)
id.to_csv("./id_"+scenario+"_"+RCP+"_"+extension+"_18052021.csv")


## Create some new variables in the data

columnTypes = {
    'i_Vm3':(float,"Relative to Area"),
    'Harvested_V':(float,"Relative to Area"),
    'Harvested_V_log_under_bark':(float,"Relative to Area"), 
    'Harvested_V_pulp_under_bark':(float,"Relative to Area"),
    'Harvested_V_under_bark':(float,"Relative to Area"), 
    'Biomass':(float,"Relative to Area"),
    'ALL_MARKETED_MUSHROOMS':(float,"Relative to Area"), 
    'BILBERRY':(float,"Relative to Area"), 
    'COWBERRY':(float,"Relative to Area"),
    'HSI_MOOSE':(float,"Relative to Area"),
    'CAPERCAILLIE':(float,"Relative to Area"), 
    'HAZEL_GROUSE':(float,"Relative to Area"), 
    'V_total_deadwood':(float,"Relative to Area"), 
    'N_where_D_gt_40':(float,"Relative to Area"),
    'prc_V_deciduous':(float,"Relative to Area"),
    'CARBON_SINK':(float,"Relative to Area"), 
    'Recreation':(float,"Relative to Area"),
    'Scenic':(float,"Relative to Area")
}

mfo.calculateTotalValuesFromRelativeValues(columnTypes=columnTypes)


# List the new variables created:

[name for name in mfo.data.columns if "Total_" in name and "Relative" not in name]


# ## Create new column:
# 1) Column indicating if regime is "CCF_3, CCF_4, BAUwGTR" (TRUE/FLASE) <br>
# Important for ES Biodiversity, allowed regimes for conservation sites.

# 2) Column indicating if regime is "SA" (TRUE/FALSE)<br>
# Important for ES Biodiversity, allowed regimes for statutory protection sites.

# 3) Column indicating if regime is "BAUwT_B, BAUwT_5_B, BAUwT_15_B, BAUwT_30_B, BAUwT_GTR_B" <br>
# Important for ES Resillience, allowed regimes for climate change adaption.

# 4) Column indicating if regime is within all four CCF
# Important for ES Water under GLOBIOM V2 (enabled constraint -> soft target).

regimeClassNames = {"regimeClass0name":"CCF",
                    "regimeClass1name":"SA",
                    "regimeClass2name":"Broadleave",
                    "regimeClass3name":"AllCCF"}
regimeClassregimes = {"regimeClass0regimes":["CCF_3","CCF_4","BAUwGTR"],
                      "regimeClass1regimes":["SA"],
                      "regimeClass2regimes":["BAUwT_B", "BAUwT_5_B", "BAUwT_15_B", "BAUwT_30_B", "BAUwT_GTR_B"],
                      "regimeClass3regimes":["CCF_1","CCF_2","CCF_3","CCF_4"]}

mfo.addRegimeClassifications(regimeClassNames = regimeClassNames,regimeClassregimes=regimeClassregimes)


## New column for "soft target" of only CCF on peat (ES Water)

# Column indicating if CCF and SA are on peat land - allowed regimes for water protection
mfo.data['CCFonPeat'] = np.where( 
    ( (mfo.data['AllCCF_forests'] == True ) & (mfo.data['PEAT'] == 1 ) ) | 
    ( (mfo.data['SA_forests'] == True) & (mfo.data['PEAT'] == 1 ) )
    , 1, 0
)

# Create subsample to get the total peat area
peat = mfo.data[["id","represented_area_by_NFIplot","PEAT"]]
peat = peat[(peat["PEAT"] == 1)]
peat = peat.drop_duplicates(['id'])
totalPeat = peat["represented_area_by_NFIplot"].sum() / sample # divide by the sample ratio !!
totalPeat

len(peat)

# Column defining a peat stand´s area in relation to total peat area (USED for OPTIMIZATION!)
mfo.data['peatCCFArea'] = np.where(
    (mfo.data['CCFonPeat'] == 1 ), mfo.data['represented_area_by_NFIplot'] / totalPeat, 0
)


## Define initial value:
# 1) Define initial values; initial state is recognized by the regime "initial_state"
# 
# 2) Create new variables that describe the <b>relative change to initial situation (start year) "Relative_":

mfo.finalizeData(initialRegime="initial_state")


# New variables created:

[name for name in mfo.data.columns if "Relative_" in name]

mfo.data.head()

mfo.initialData.head()


## Start defining the optimization problem
## Group objective by ecosystem services

wood_production = { 
    # Increment
    "Sum_i_Vm3": ["Annual timber volume increment(m3)",
                  "i_Vm3","max","min","areaWeightedSum"], 
    # Harvested volume
    "Sum_Harvested_V" :["Annual harvested timber volume (m3)",
                        "Harvested_V","max","min","areaWeightedSum"] 
}

bioenergy = { 
    # Biomass
    "Sum_Biomass": ["Annual harvested biomass volume (m3)",
                    "Biomass","max","min","areaWeightedSum"]
}

nonwood = { 
    # Bilberries 
    "Sum_BILBERRY": ["Bilberry yield (kg)",
                     "BILBERRY","max","min","areaWeightedSum"],
    # Cowberries
    "Sum_COWBERRY": ["Cowberry yield (kg)",
                     "COWBERRY","max","min","areaWeightedSum"],
    # Mushrooms
    "Sum_ALL_MARKETED_MUSHROOMS": ["Marketed mushroom yield (kg)",
                                   "ALL_MARKETED_MUSHROOMS","max","min","areaWeightedSum"]    
}

game = {
    # Moose
    "Sum_HSI_MOOSE": ["Habitat index for MOOSE (index)",
                      "HSI_MOOSE","max","average","areaWeightedSum"],
    # Hazel Grouse
    "Sum_HAZEL_GROUSE": ["Habitat index for HAZEL_GROUSE (index)",
                         "HAZEL_GROUSE","max","average","areaWeightedSum"],
    # Capercaillie
    "Sum_CAPERCAILLIE": ["Habitat index for CAPERCAILLIE (index)",
                         "CAPERCAILLIE","max","average","areaWeightedSum"]    
}

biodiversity = {
    # Share of set aside - same objective fct. as in policies
    #"Ratio_SA_forests": ["Ratio of protected areas (%, SA forests)",
    #                     "SA_forests","max","firstYear","areaWeightedAverage"],   
    
    # Share of conservation management - same objective fct. as in policies
    "Ratio_CCF_forests": ["Ratio of BC sites in commercial forests (%, CCF_3, CCF_4 and BAUwGTR)",
                          "CCF_forests","max","firstYear","areaWeightedAverage"],
    # Deadwood
    "Sum_Deadwood_V": ["Deadwood volume (m3)", 
                       "V_total_deadwood","max","min","areaWeightedSum"], 
    # Deciduous trees (% of volume)
    "Sum_prc_V_deciduous":  ["Share of deciduous trees (% of standing volume)", 
                             "prc_V_deciduous","max", "min","areaWeightedSum"],
    # Large trees
    "Sum_N_where_D_gt_40": ["No. of large trees DBH >= 40 cm  (per ha)",
                            "N_where_D_gt_40","max","min","areaWeightedSum"]    
}

climate_regulation = {
    # Carbon sink
    "Sum_CARBON_SINK": ["Sequestration of carbon dioxide (t CO2)",
                        "CARBON_SINK", "max","min","areaWeightedSum"] 
}

recreation = {
    # Recreation index
    "Sum_Recreation": ["Recreation index (-)",
                       "Recreation","max","min","areaWeightedSum"],
    # Scenic beauty index
    "Sum_Scenic": ["Scenic index (-)",
                   "Scenic","max","min","areaWeightedSum"]
}

resilience = {
    # Share of Adaption to Climate Change (ACC) management - same objective fct. as in policies
    "Ratio_ACC_forests": ["Ratio of adaptive management regimes (%, ..._B regimes)",
                          "Broadleave_forests","max","firstYear","areaWeightedAverage"]
}

water = {
    # Share of CCF management on peat - same objective fct. as in policies
    "Ratio_CCF_onPeat": ["Ratio of CCF on Peatland (%, all four CCF and SA)",
                         "peatCCFArea","max", "firstYear", "sum"]         
}


objectives = {**wood_production,
              **bioenergy,
              #**nonwood,
              #**game,
              **biodiversity,
              **climate_regulation,
              **recreation,
              **resilience,
              **water
}

len(objectives)

objectives.keys()

mfo.data.columns

[(col,mfo.data.dtypes[col]) for col in mfo.data.columns if "prc" in col]



## Define initial values if not available in data (initial_state)

#initialValues = {"Total_i_Vm3":107*10**6,               # value from National Forest Policy
#                 "Total_Harvested_V": 72.3*10**6,       # value from National Forest Policy
#                 "Total_Biomass": 2.9*10**6,            # value from National Forest Policy
#                 "Total_CARBON_SINK" : 34.1*10**6,      # value from National Forest Policy
#                                 
#                 "SA_forests" : 0.106,     # from ForestStatistics 2018
#                 "CCF_forests" : 0.015,    # from ForestStatistics 2018
#                 "BAUwGTR_forests":0.015}  # from ForestStatistics 2018


#mfo.defineObjectives(objectives, initialValues = initialValues)
mfo.defineObjectives(objectives) 


## Define the constraints

#CCFregimes = [regime for regime in mfo.regimes if "CCF" in regime] + ["SA"]

#CCFregimes

#constraintTypes = {"CCFonPeat":["Allowed regimes","Only CCF on peat lands",CCFregimes,"PEAT"]}

#mfo.defineConstraints(constraintTypes)


## Calculate objective ranges

mfo.data

mfo.calculateObjectiveRanges(debug=True)

mfo.objectiveRanges


# ------------
# NEW - optimize for maximum Multifunctionality
# ------------

# Following Eyvindson et al. (2021)


## Define the ecosystem service categories

ESS = {'wood_production':wood_production,
       'bioenergy':bioenergy,
       #'nonwood':nonwood,
       #'game':game,
       'biodiversity':biodiversity,
       'climate_regulation':climate_regulation,
       'recreation':recreation,
       'resilience':resilience,
       'water':water}


## Define how solutions by ESS are going to be aggregated

# Based on the minimum value (MIN) or average value (AVG) for each group.
# SOME LOGIC IS NEEDED FOR THIS. Is there only 1 objective in a ESS group, it doesn't matter. Has an ESS group multiple objectives, it does matter. 

AGG = {'wood_production':"AVG",
       'bioenergy':"AVG",
       #'nonwood':"AVG",
       #'game':"MIN",
       'biodiversity':"MIN",
       'climate_regulation':"AVG",
       'recreation':"MIN",
       'resilience':"AVG",
       'water':"AVG"}

mfo.addEyvindsonMultifunctionality(ESS,AGG)

mfo.solveMultifunctionality()


## Export data as csv

try:
    os.mkdir("results")
except FileExistsError:
    pass
b = []
c = []
for key in mfo.regimesDecision.keys():
    if mfo.regimesDecision[key].solution_value() > 0:
        b = b+ [(key[0],x*5+2016, key[1]) for x in range(0,21)]
        c = c+ [(key[0],key[1],mfo.regimesDecision[key].solution_value())]
data2b = mfo.data.iloc[mfo.data.index.isin(b)]
data2b.to_csv("./results/solution_alldata_"+scenario+"_"+RCP+"_"+extension+".csv")
c1 = pd.DataFrame(c)
c1.to_csv("./results/solution_"+scenario+"_"+RCP+"_"+extension+".csv")


## Export objective ranges

import json
mfo.objectiveRanges

with open('./results/objectiveRanges_'+scenario+'_'+RCP+'_'+extension+'.json', 'w') as json_file:
    json.dump(mfo.objectiveRanges, json_file)

df = pd.read_json('./results/objectiveRanges_'+scenario+'_'+RCP+'_'+extension+'.json')

df.to_csv('./results/objectiveRanges_'+scenario+'_'+RCP+'_'+extension+'.csv')


## Export objective values

with open("./results/objectiveValues_"+scenario+'_'+RCP+'_'+extension+".csv","w") as file: 
    delim = "" 
    for objName in mfo.objectiveTypes.keys(): 
        file.write(delim+objName) 
        delim = "," 
    file.write("\n") 
    delim = "" 
    for objName in mfo.objectiveTypes.keys(): 
        file.write(delim+str(mfo.objective[objName].solution_value())) 
        delim = "," 
    file.write("\n")
    
    

