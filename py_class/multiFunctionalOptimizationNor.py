import pandas as pd
import numpy as np
import wget
import os

from datetime import datetime

from ortools.linear_solver import pywraplp

import itertools

import ipywidgets as widgets
from IPython.display import display, HTML

from tqdm import tqdm
import sys

class MultiFunctionalOptimization:

    data = pd.DataFrame()
    columnTypes = {}
    initialData = pd.DataFrame()

    regimes = list()
    years = list()
    standIds = list()

    standAreas = pd.DataFrame()
    peat = pd.DataFrame()

    constraints = dict()

    solutionCounter = 0

    debug = False


    # Open source solver, if commercial is not available
    def __init__(self,solver="CLP"):
        if solver == "CLP":
            self.solver = pywraplp.Solver('MultiForest Optimization Problem',
                            pywraplp.Solver.CLP_LINEAR_PROGRAMMING)
            display("Using CLP")
        elif solver == "CPLEX":
            self.solver = pywraplp.Solver('MultiForest Optimization Problem',
                            pywraplp.Solver.CPLEX_LINEAR_PROGRAMMING)
            display("Using CPLEX")
        elif solver == "GLOP":
            self.solver = pywraplp.Solver('MultiForest Optimization Problem',
                            pywraplp.Solver.GLOP_LINEAR_PROGRAMMING)
            display("Using GLOP")
        else:
            display("Undefined solver, using CLP")     
            self.solver = pywraplp.Solver('MultiForest Optimization Problem',
                            pywraplp.Solver.CLP_LINEAR_PROGRAMMING)
        

    def readData(self,filename,sampleRatio=1,delimeter=";",
                standsEnu = "id",regimesEnu = ["regime"],timeEnu = "year",
                areaCol = "represented_area_by_NFIplot"):
        self.sampleRatio = sampleRatio
        self.areaCol = areaCol
        self.timeEnu = timeEnu
        try:
            self.data = pd.read_hdf(filename.split(".")[0]+".h5",key="df")
        except:
            self.data = pd.read_csv(filename,delimiter=delimeter)
            self.data.to_hdf(filename.split(".")[0]+".h5",key="df")
        self.standsEnu = standsEnu
        if len(regimesEnu) == 1:
            self.regimesEnu = regimesEnu[0]
        else:
            self.regimesEnu = "combinedRegime"
            self.data["combinedRegime"] = [""]*len(self.data)
            for i,colname in enumerate(regimesEnu):
                self.data["combinedRegime"]+=[colname]*len(self.data)
                self.data["combinedRegime"]+=self.data[colname].astype(str).values
                if i < len(regimesEnu)-1:
                    self.data["combinedRegime"]+=["_"]*len(self.data)
        self.data.replace(np.nan,0,inplace=True)
        if sampleRatio < 1:
            n = int(len(set(self.data[self.standsEnu].values))*sampleRatio)
            stand_sample = np.random.choice(list(set(self.data[self.standsEnu].values)),n,replace=False)
            display("sample size "+str(n)+"/"+str(len(set(self.data[self.standsEnu].values)))+"("+str(int(n/len(set(self.data[self.standsEnu].values))*100))+"%)")
            self.data = self.data[self.data[self.standsEnu].isin(stand_sample)]

    def CalculateTotalValues(self,**kwargs):
        self.columnTypes = kwargs
        for colname in self.data.columns:
            try:
                self.data[colname] = self.data[colname].astype(self.columnTypes[colname][0]).values
                if self.columnTypes[colname][1] == "Relative to Area":
                    self.data["Total_"+colname]=self.data[colname].values*self.data["represented_area_by_NFIplot"].values
                elif self.columnTypes[colname][1] == "Relative to Volume":
                    self.data["Total_"+colname]=self.data[colname].values*self.data["V"].values
            except KeyError:
                if not colname in [self.timeEnu,self.regimesEnu,self.standsEnu]:
                    self.data[colname] = pd.to_numeric(self.data[colname],errors="ignore").values

    
    def calculateTotalValuesFromRelativeValues(self,columnTypes = dict()):
        if len(columnTypes) > 0: #If data about column types is given use that
            self.CalculateTotalValues(**columnTypes)
        else: ##If no data is given show a gui for selecting data
            colTypeChooser = widgets.interactive(self.CalculateTotalValues,{"manual":True},**{colname:["Absolute Value","Relative to Area","Relative to Volume"] for colname in self.data.columns})
            display(HTML('''<style>
                .widget-label { min-width: 60% !important; }
            </style>'''))
            display(colTypeChooser)

    def addRegimes(self,**kwargs):
        for i in range(10):
            try:
                if len(kwargs["regimeClass"+str(i)+"name"])>0:
                    self.data[kwargs["regimeClass"+str(i)+"name"]+"_forests"] = self.data[self.regimesEnu].isin(kwargs["regimeClass"+str(i)+"regimes"])
            except KeyError:
                pass
    def addRegimeClassifications(self,regimeClassNames = dict(),regimeClassregimes=dict()):
        if len(regimeClassNames) > 0:
            self.addRegimes(**regimeClassNames,**regimeClassregimes)
        else:
            regimeClassificationChooser = widgets.interactive(self.addRegimes,{"manual":True},
            **{"regimeClass"+str(i)+"name":widgets.Text() for i in range(10)},
            **{"regimeClass"+str(i)+"regimes":widgets.SelectMultiple(options=tuple(self.data["regimesEnu"].unique())) for i in range(10)})
            display(regimeClassificationChooser)

    def finalizeData(self,
                initialRegime = "",initialTime = -np.inf):
        initialRequirement = np.array([True]*len(self.data))
        if len(initialRegime) > 0:
            initialRequirement = initialRequirement*np.array(self.data[self.regimesEnu] == initialRegime)
        if initialTime > -np.inf:
            initialRequirement = initialRequirement*np.array(self.data[self.timeEnu] == initialTime)
        if len(initialRegime)>0 or initialTime>-np.inf:
            #Define initial data if such available
            self.initialData = self.data[initialRequirement]
            self.data = self.data[~initialRequirement]
            self.initialData.set_index([self.standsEnu,self.timeEnu,self.regimesEnu],inplace=True)
            self.initialData.sort_index(inplace=True)
            self.initialYear = min(self.initialData.index.get_level_values(self.timeEnu))
        self.data.set_index([self.standsEnu,self.timeEnu,self.regimesEnu],inplace=True)
        self.data.sort_index(inplace=True)
        #Use initialdata to define relative values if possible
        if len(initialRegime)>0 or initialTime>-np.inf: 
            for colname in self.data.columns:
                try:
                    if self.initialData.dtypes[colname] == float  and self.initialData[colname].sum()>0:
                        self.data["Relative_"+colname] = self.data[colname]/self.initialData[colname].sum()
                except (NameError,KeyError) as _:
                    pass
        self.regimes = self.data.index.get_level_values(self.regimesEnu).unique()
        self.years = self.data.index.get_level_values(self.timeEnu).unique()
        self.standIds = self.data.index.get_level_values(self.standsEnu).unique()

        self.standAreas = self.data.loc[(slice(None),self.years[0],slice(None)),self.areaCol]
        self.standAreas = self.standAreas.reset_index()
        self.standAreas.drop([self.regimesEnu,self.timeEnu],axis=1,inplace=True)
        self.standAreas.drop_duplicates(inplace=True)
        self.standAreas.set_index(self.standsEnu,inplace=True)
        self.standAreas.sort_index(inplace=True)


    def addConstraints(self,constraintTypes):
        self.constraintTypes = constraintTypes
        self.speciesValues = dict()
        for constraintName in self.constraintTypes.keys():
            if self.constraintTypes[constraintName][0] == "Allowed regimes":
                self.constraints[constraintName] = dict()
                for regime in self.regimes:
                    if regime not in self.constraintTypes[constraintName][2]:
                        for standId in self.standIds:
                            if (standId,regime) in self.regimesDecision.keys() and self.data.loc[(standId,self.years[0],regime),self.constraintTypes[constraintName][3]] == 1:
                                self.constraints[constraintName][(standId,regime)] = self.solver.Add(self.regimesDecision[(standId,regime)]<=1,name = "No"+regime+"with"+self.constraintTypes[constraintName][3]+"onStand"+str(standId))
            if self.constraintTypes[constraintName][0] == "Species reduction":
                speciesCol = self.constraintTypes[constraintName][2]
                periodNo = self.constraintTypes[constraintName][3]
                reductionAmount = self.constraintTypes[constraintName][4]
                self.constraints[constraintName] = dict()
                for i,year in enumerate(self.years):
                    self.speciesValues[(speciesCol,year)] = self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),speciesCol+"amountInyear"+str(year))
                    self.solver.Add(self.speciesValues[(speciesCol,year)] ==
                        sum(self.decisionFrame["Decision"].values*
                                        self.data.loc[(slice(None),year,slice(None)),speciesCol].values)/self.sampleRatio,
                        name="constraintforSpeciesDec"+speciesCol+"InYear"+str(year))
                    if i>= periodNo:
                        self.constraints[constraintName][year] = self.solver.Add(self.speciesValues[(speciesCol,year)]-(1-reductionAmount)*self.speciesValues[(speciesCol,year-periodNo*5)]>=-1e10)
                        
            if self.constraintTypes[constraintName][0] == "Species increase":
                speciesCol = self.constraintTypes[constraintName][2]
                periodNo = self.constraintTypes[constraintName][3]
                reductionAmount = self.constraintTypes[constraintName][4]
                self.constraints[constraintName] = dict()
                display(self.constraintTypes[constraintName][0] )
                
                for i,year in enumerate(self.years):
                    self.speciesValues[(speciesCol,year)] = self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),speciesCol+"amountInyear"+str(year))
                    
                    self.solver.Add(self.speciesValues[(speciesCol,year)] ==
                        sum(self.decisionFrame["Decision"].values*
                                        self.data.loc[(slice(None),year,slice(None)),speciesCol].values)/self.sampleRatio,
                        name="constraintforSpeciesInc"+speciesCol+"InYear"+str(year))
                    if i>= periodNo:
                        self.constraints[constraintName][year] = self.solver.Add(self.speciesValues[(speciesCol,year)]- (1 + reductionAmount) * self.speciesValues[(speciesCol, year - periodNo*5)]  <= 1e10,name = speciesCol + "valuePer"+str(periodNo)+"inYear"+str(year))
                        
            if self.constraintTypes[constraintName][0] == "less than":
                colname1 = self.constraintTypes[constraintName][2]
                colname2 = self.constraintTypes[constraintName][3]
                standWiseAggregation1 = self.constraintTypes[constraintName][4]
                standWiseAggregation2 = self.constraintTypes[constraintName][5]
                self.constraints[constraintName] = dict()
                self.comparedValues = dict()
                for regime in self.regimes:
                    for year in self.years:
                        self.comparedValues[(colname1,year)] = self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),colname1+"amountInyear"+str(year))
                        self.comparedValues[(colname2,year)] = self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),colname2+"amountInyear"+str(year))
                        if standWiseAggregation1 == "sum":
                            # import pdb; pdb.set_trace()
                            if not "Relative_" in colname1:
                                self.solver.Add(self.comparedValues[(colname1,year)] ==
                                        sum(self.decisionFrame["Decision"].values*
                                                        self.data.loc[(slice(None),year,slice(None)),colname1].sort_index().values)/self.sampleRatio,
                                        name="constraintfor"+colname1+"comparisonInYear"+str(year))
                            else:
                                    self.solver.Add(self.comparedValues[(colname1,year)] ==
                                        sum(self.decisionFrame["Decision"].values*
                                                        self.data.loc[(slice(None),year,slice(None)),colname1].sort_index().values),
                                        name="constraintfor"+colname1+"comparisonInYear"+str(year))
                        elif standWiseAggregation1 == "areaWeightedAverage":
                            self.solver.Add(self.comparedValues[(colname1,year)]==
                                    sum(self.decisionFrame["Decision"].values*
                                                    (self.data.loc[(slice(None),year,slice(None)),colname1].sort_index().values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].sort_index().values))/self.standAreas.values.sum(),
                                    name="constraintfor"+colname1+"comparisonInYear"+str(year))
                        elif standWiseAggregation1 == "areaWeightedSum":
                            if not "Relative_" in colname1:
                                self.solver.Add(self.comparedValues[(colname1,year)] ==
                                sum(self.decisionFrame["Decision"].values*
                                                (self.data.loc[(slice(None),year,slice(None)),colname1].sort_index().values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].sort_index().values))/self.sampleRatio,
                                name="constraintfor"+colname1+"comparisonInYear"+str(year))
                            else:
                                self.solver.Add(self.comparedValues[(colname1,year)] ==
                                sum(self.decisionFrame["Decision"].values*
                                                (self.data.loc[(slice(None),year,slice(None)),colname1].sort_index().values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].sort_index().values)),
                                name="constraintfor"+colname1+"comparisonInYear"+str(year))
                        if standWiseAggregation2 == "sum":
                            # import pdb; pdb.set_trace()
                            if not "Relative_" in colname2:
                                self.solver.Add(self.comparedValues[(colname2,year)] ==
                                        sum(self.decisionFrame["Decision"].values*
                                                        self.data.loc[(slice(None),year,slice(None)),colname2].sort_index().values)/self.sampleRatio,
                                        name="constraintfor"+colname2+"comparisonInYear"+str(year))
                            else:
                                    self.solver.Add(self.comparedValues[(colname2,year)] ==
                                        sum(self.decisionFrame["Decision"].values*
                                                        self.data.loc[(slice(None),year,slice(None)),colname2].sort_index().values),
                                        name="constraintfor"+colname2+"comparisonInYear"+str(year))
                        elif standWiseAggregation2 == "areaWeightedAverage":
                            self.solver.Add(self.comparedValues[(colname2,year)]==
                                    sum(self.decisionFrame["Decision"].values*
                                                    (self.data.loc[(slice(None),year,slice(None)),colname2].sort_index().values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].sort_index().values))/self.standAreas.values.sum(),
                                    name="constraintfor"+colname2+"comparisonInYear"+str(year))
                        elif standWiseAggregation2 == "areaWeightedSum":
                            if not "Relative_" in colname2:
                                self.solver.Add(self.comparedValues[(colname2,year)] ==
                                sum(self.decisionFrame["Decision"].values*
                                                (self.data.loc[(slice(None),year,slice(None)),colname2].sort_index().values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].sort_index().values))/self.sampleRatio,
                                name="constraintfor"+colname2+"comparisonInYear"+str(year))
                            else:
                                self.solver.Add(self.comparedValues[(colname2,year)] ==
                                sum(self.decisionFrame["Decision"].values*
                                                (self.data.loc[(slice(None),year,slice(None)),colname2].sort_index().values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].sort_index().values)),
                                name="constraintfor"+colname2+"comparisonInYear"+str(year))
                        self.constraints[constraintName][year] = self.solver.Add(self.comparedValues[(colname1,year)]-self.comparedValues[(colname2,year)]<=10e10
                            ,name = colname1 + "lessThan"+colname2+"inYear"+str(year))


    def defineConstraints(self,constraintTypes):
        if len(constraintTypes) > 0:
            self.addConstraints(constraintTypes)
        else:
            pass
            ## TODO think about GUI

    def addObjectives(self,objectiveTypes,initialValues):
        self.objectiveTypes = objectiveTypes

        display("Defining objectives")
                
        self.decisionFrame = pd.DataFrame(pd.Series(self.regimesDecision))
        self.decisionFrame.columns = ["Decision"]
        self.decisionFrame.sort_index(inplace=True)

        self.objectivesByYear = dict()
        for objName in self.objectiveTypes.keys():
            for year in self.years:
                self.objectivesByYear[(objName,year)] = self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),objName+"year"+str(year))

        self.maxDummyConstraints = {objName:
                        self.solver.Constraint(-self.solver.infinity(),self.solver.infinity(),"maxDummyConstraintfor"+objName)
                        for objName in self.objectiveTypes.keys()}
        self.maxDummy = self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),"DummyVar")
        self.initialValues = dict()

        display("Aggregating stand wise")
        # Stand wise aggregation
        for objName in tqdm(self.objectiveTypes.keys()):
            if self.objectiveTypes[objName][4] == "sum":
                for year in self.years:
                    if not "Relative_" in self.objectiveTypes[objName][1]:
                        self.solver.Add(self.objectivesByYear[(objName,year)] ==
                                sum(self.decisionFrame["Decision"].values*
                                                self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][1]].values)/self.sampleRatio,
                                name="constraintfor"+objName+"InYear"+str(year))
                    else:
                            self.solver.Add(self.objectivesByYear[(objName,year)] ==
                                sum(self.decisionFrame["Decision"].values*
                                                self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][1]].values),
                                name="constraintfor"+objName+"InYear"+str(year))
                try:
                    if "Relative_" in self.objectiveTypes[objName][1]:
                        self.initialValues[objName] = 1
                    else:
                        try:
                            self.initialValues[objName] = initialValues[objName]
                        except KeyError:
                            self.initialValues[objName] = self.initialData.loc[(slice(None),slice(None),slice(None)),self.objectiveTypes[objName][1]].values.sum()
                except NameError:
                    pass
            elif self.objectiveTypes[objName][4] == "areaWeightedAverage":
                for year in self.years:
                    self.solver.Add(self.objectivesByYear[(objName,year)]==
                            sum(self.decisionFrame["Decision"].values*
                                            (self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][1]].values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].values))/self.standAreas.values.sum(),
                            name="constraintfor"+objName+"InYear"+str(year))
                try:

                    if "Relative_" in self.objectiveTypes[objName][1]:
                        self.initialValues[objName] = 1
                    else:
                        try:
                            self.initialValues[objName] = initialValues[objName]
                        except KeyError:
                            self.initialValues[objName] = self.initialData.loc[(slice(None),slice(None),slice(None)),self.objectiveTypes[objName][1]].values.sum()
                except NameError:
                    pass
            elif self.objectiveTypes[objName][4] == "areaWeightedSum":
                for year in self.years:
                        if not "Relative_" in self.objectiveTypes[objName][1]:
                            self.solver.Add(self.objectivesByYear[(objName,year)] ==
                            sum(self.decisionFrame["Decision"].values*
                                            (self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][1]].values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].values))/self.sampleRatio,
                            name="constraintfor"+objName+"InYear"+str(year))
                        else:
                            self.solver.Add(self.objectivesByYear[(objName,year)] ==
                            sum(self.decisionFrame["Decision"].values*
                                            (self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][1]].values*self.data.loc[(slice(None),year,slice(None)),self.areaCol].values)),
                            name="constraintfor"+objName+"InYear"+str(year))
  
                try:
                    if "Relative_" in self.objectiveTypes[objName][1]:
                        self.initialValues[objName] = 1
                    else:
                        try:
                            self.initialValues[objName] = initialValues[objName]
                        except KeyError:
                            self.initialValues[objName] = self.initialData.loc[(slice(None),slice(None),slice(None)),self.objectiveTypes[objName][1]].values.sum()
                except NameError:
                    pass
            elif self.objectiveTypes[objName][4] == "subsetSum":
                for year in self.years:
                    if not "Relative_" in self.objectiveTypes[objName][1]:
                        self.solver.Add(self.objectivesByYear[(objName,year)] ==
                                sum(self.decisionFrame["Decision"].values*
                                                (self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][1]].values*self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][-1]].values))/self.sampleRatio,
                                name="constraintfor"+objName+"InYear"+str(year))
                    else:
                        self.solver.Add(self.objectivesByYear[(objName,year)] ==
                                sum(self.decisionFrame["Decision"].values*
                                                (self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][1]].values*self.data.loc[(slice(None),year,slice(None)),self.objectiveTypes[objName][-1]].values)),
                                name="constraintfor"+objName+"InYear"+str(year))
                try:
                    if "Relative_" in self.objectiveTypes[objName][1]:
                        self.initialValues[objName] = 1
                    else:
                        try:
                            self.initialValues[objName] = initialValues[objName]
                        except KeyError:
                            self.initialValues[objName] = self.initialData.loc[(slice(None),slice(None),slice(None)),self.objectiveTypes[objName][1]].values.sum()
                except NameError:
                    pass           

        self.objective = {
            objShortName:self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),objShortName)
            for objShortName in self.objectiveTypes.keys()
        }

        display("Aggregating year wise")
        # Year wise aggregation
        for objName in tqdm(self.objectiveTypes.keys(),file=sys.stdout):
            if self.objectiveTypes[objName][3] == "min":
                for year in self.years:
                    self.solver.Add(self.objective[objName]<=self.objectivesByYear[(objName,year)])
            elif self.objectiveTypes[objName][3] == "max":
                for year in self.years:
                    self.solver.Add(self.objective[objName]>=self.objectivesByYear[(objName,year)])
            elif self.objectiveTypes[objName][3] == "average":
                self.solver.Add(self.objective[objName]==sum([self.objectivesByYear[(objName,year)] for year in self.years])/len(self.years))
            elif self.objectiveTypes[objName][3] == "firstYear":
                self.solver.Add(self.objective[objName]==self.objectivesByYear[(objName,self.years[0])])
            elif self.objectiveTypes[objName][3] == "lastYear":
                self.solver.Add(self.objective[objName]==self.objectivesByYear[(objName,self.years[-1])])
            elif self.objectiveTypes[objName][3] == "sum":
                self.solver.Add(self.objective[objName]==sum([self.objectivesByYear[(objName,year)] for year in self.years]))
            elif self.objectiveTypes[objName][3] == "minYearlyIncrease":
                for i,year in enumerate(self.years):
                    if i>=1:
                        self.solver.Add(self.objective[objName]<=self.objectivesByYear[(objName,self.years[i])]-self.objectivesByYear[(objName,self.years[i-1])])
            elif self.objectiveTypes[objName][3] == "maxYearlyIncrease":
                for i,year in enumerate(self.years):
                    if i>=1:
                        self.solver.Add(self.objective[objName]>=self.objectivesByYear[(objName,self.years[i])]-self.objectivesByYear[(objName,self.years[i-1])])
            elif self.objectiveTypes[objName][3] == "maxDecreaseDuringNPeriods":
                for i,year in enumerate(self.years):
                    if i>=self.objectiveTypes[objName][-1]:
                        self.solver.Add(self.objective[objName]>=self.objectivesByYear[(objName,self.years[i])]-self.objectivesByYear[(objName,self.years[i-self.objectiveTypes[objName][-1]])])
            elif self.objectiveTypes[objName][3] == "minIncreaseDuringNPeriods":
                for i,year in enumerate(self.years):
                    if i>=self.objectiveTypes[objName][-1]:
                        self.solver.Add(self.objective[objName]<=self.objectivesByYear[(objName,self.years[i])]-self.objectivesByYear[(objName,self.years[i-self.objectiveTypes[objName][-1]])])
            elif self.objectiveTypes[objName][3] == "targetYearWithSlope":
                targetYear = self.objectiveTypes[objName][-1]
                for year in self.years:
                    if year <= targetYear:
                        coeff = float(year-self.initialYear)/float(targetYear-self.initialYear)
                        self.solver.Add(self.objectivesByYear[(objName,year)] >= (1-coeff)*self.initialValues[objName]+coeff*self.objective[objName])
                    if year > targetYear:
                        self.solver.Add(self.objectivesByYear[(objName,year)] >= self.objective[objName] )
            elif self.objectiveTypes[objName][3] == "targetYear":
                targetYear = self.objectiveTypes[objName][-1]
                for i,year in enumerate(self.years):
                    if (i == 0 and year >targetYear) or (self.years[i-1] < targetYear and year > targetYear):
                        self.solver.Add(self.objectivesByYear[(objName,year)] == self.objective[objName] )
            elif self.objectiveTypes[objName][3] == "periodicTargets":
                periodicTargets = self.objectiveTypes[objName][-1]
                for i,year in enumerate(self.years):
                    self.solver.Add(self.objective[objName] <= (self.objectivesByYear[(objName,year)]-periodicTargets[i])/periodicTargets[i])
            else:
                display("Undefined yearly aggregation "+self.objectiveTypes[objName][3])
        display("Objectives added")

    def defineObjectives(self,objectiveTypes,initialValues=dict()):

        self.regimesDecision = {(standId,regime):
                   self.solver.NumVar(0,1,"treatmentDecisionForStand"+str(standId)+"Regime"+regime) 
                   for (standId,regime) in itertools.product(self.standIds,self.regimes) if (standId,self.years[0],regime) in self.data.index}
        for standId in self.standIds:
            self.solver.Add(sum([self.regimesDecision[(standId,regime)] for regime in self.regimes if (standId,self.years[0],regime) in self.data.index])==1,name = "regimeConstraintForStand"+str(standId))
        if len(objectiveTypes) > 0:
            self.addObjectives(objectiveTypes,initialValues)
        else:
            pass
            ## TODO think about GUI

    def addGlobiomTargets(self,targetDict,transferRates,exactMatching=False):
        #TODO check that addobjectives has been run so that self.objectiveTypes exists
        sources = list(transferRates.keys())
        self.globiomProduction = dict()
        self.globiomTargets = targetDict
        for source in sources:
            self.globiomProduction[source] = dict()
            for year in self.years:
                self.globiomProduction[source][year] = dict()
                for target in transferRates[source].keys():
                   self.globiomProduction[source][year][target] = self.solver.NumVar(0,self.solver.infinity(),name=source+"UsedForGlobiomTarget"+target+"inYear"+str(year))
        self.globiomConstraint = dict()
        for source in sources:
            self.globiomConstraint[source] = dict()
            for year in self.years:
                targets = transferRates[source].keys()
                self.globiomConstraint[source][year] = self.solver.Add(sum(self.globiomProduction[source][year][target] for target in targets) 
                == sum(self.decisionFrame["Decision"].values*self.data.loc[(slice(None),year,slice(None)),source].sort_index().values)/self.sampleRatio,
                name = "GlobiomConstraintforsource"+source+"InYear"+str(year))
        targets = targetDict.keys()
        for target in targets:
            self.objectiveTypes["GlobiomTargetFor"+target] = [""]*5
            self.objectiveTypes["GlobiomTargetFor"+target][0] = "Relative meeting of globiom target for "+target
            if not exactMatching:
                self.objectiveTypes["GlobiomTargetFor"+target][2] = "max"
            else:
                self.objectiveTypes["GlobiomTargetFor"+target][2] = "min"
            self.objective["GlobiomTargetFor"+target] = self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),"GlobiomTargetFor"+target)
            self.maxDummyConstraints["GlobiomTargetFor"+target] = self.solver.Constraint(-self.solver.infinity(),self.solver.infinity(),"maxDummyConstraintforGlobiomTargetFor"+target)
            for i,year in enumerate(self.years):
                if not exactMatching:
                    self.solver.Add(self.objective["GlobiomTargetFor"+target]<= 
                    sum(np.array([self.globiomProduction[source][year][target] for source in sources if target in transferRates[source].keys()])*
                    np.array([transferRates[source][target][0] for source in sources if target in transferRates[source].keys()]))
                    /targetDict[target][i],
                    name="GlobiomConstraintforTarget"+target)
                else:
                    self.solver.Add(self.objective["GlobiomTargetFor"+target]>= 
                    sum(np.array([self.globiomProduction[source][year][target] for source in sources if target in transferRates[source].keys()])*
                    np.array([transferRates[source][target][0] for source in sources if target in transferRates[source].keys()]))-targetDict[target][i],
                    name="GlobiomConstraint1forTarget"+target)
                    self.solver.Add(self.objective["GlobiomTargetFor"+target]>= 
                    targetDict[target][i]-sum(np.array([self.globiomProduction[source][year][target] for source in sources if target in transferRates[source].keys()])*np.array([transferRates[source][target][0] for source in sources if target in transferRates[source].keys()])),
                    name="GlobiomConstraint2forTarget"+target)
        for source in sources:
            for target in transferRates[source].keys():
                if transferRates[source][target][1] == "secondary":
                    self.objectiveTypes["GlobiomSecondaryUsageof"+source+"as"+target] = [""]*5
                    self.objectiveTypes["GlobiomSecondaryUsageof"+source+"as"+target][0] = "Usage of "+source+" as "+target+" in Globiom demands"
                    self.objectiveTypes["GlobiomSecondaryUsageof"+source+"as"+target][2] = "min"
                    self.objective["GlobiomSecondaryUsageof"+source+"as"+target] = self.solver.NumVar(-self.solver.infinity(),self.solver.infinity(),"GlobiomSecondaryUsageof"+source+"as"+target)
                    self.maxDummyConstraints["GlobiomSecondaryUsageof"+source+"as"+target] = self.solver.Constraint(-self.solver.infinity(),self.solver.infinity(),"maxDummyConstraintforGlobiomTargetFor"+target)
                    self.solver.Add(self.objective["GlobiomSecondaryUsageof"+source+"as"+target] == sum(self.globiomProduction[source][year][target] for year in self.years),
                        name="GlobiomSecondaryUsageConstraintof"+source+"as"+target)

    def calculateObjectiveRanges(self,debug=False):
        self.debug=debug
        lb = {objName:np.inf for objName  in self.objectiveTypes.keys()}
        ub = {objName:-np.inf for objName  in self.objectiveTypes.keys()}
        
        display("Calculating objective ranges")
        for i,objName in enumerate(tqdm(self.objectiveTypes.keys(),file=sys.stdout)):
            self.objectiveFunction = self.solver.Objective()
            display("Optimizing for "+self.objectiveTypes[objName][0])
            self.objectiveFunction.SetMaximization()
            if self.objectiveTypes[objName][2] == "max":
                multiplier = 1
            elif self.objectiveTypes[objName][2] == "min":
                multiplier = -1
            for objName2 in self.objectiveTypes.keys():
                if objName == objName2:
                    self.objectiveFunction.SetCoefficient(self.objective[objName2],multiplier)
                else:
                    # If ranges already calculated also add the other objectives with small coefficients to improve ranges:
                    try:
                        self.objectiveFunction.SetCoefficient(self.objective[objName2],multiplier*1e-6/(self.objectiveRanges[objName2][1]-self.objectiveRanges[objName2][0]))
                    except AttributeError:
                        self.objectiveFunction.SetCoefficient(self.objective[objName2],0)                        
            #If we have already been running the GUI, then we need to remove maxDummy from objective function
            try:
                self.objectiveFunction.SetCoefficient(self.maxDummy,0)
            except AttributeError:
                pass
            if self.debug:
                problem = self.solver.ExportModelAsLpFormat(obfuscated=False)
                print(problem,file=open("problem.lp","w"))
            now = datetime.now()
            res = self.solver.Solve()
            time = datetime.now() - now 
            self.solutionTimeStamp = str(now).replace(":"," ")
            if res == self.solver.OPTIMAL:
                display("Found an optimal solution in "+str(time.seconds)+" seconds")
                display("Objective values are:")
                for i,objName in enumerate(self.objectiveTypes.keys()):
                    display(self.objectiveTypes[objName][0],self.objective[objName].solution_value())
                    if self.objective[objName].solution_value() > ub[objName]:
                        ub[objName] = self.objective[objName].solution_value()
                    if self.objective[objName].solution_value() < lb[objName]:
                        lb[objName] = self.objective[objName].solution_value()
            else:
                display("Could not solve")
                if res == self.solver.FIXED_VALUE:
                    display("Objective value fixed")
                if res == self.solver.INFEASIBLE:
                    display("Problem is infeasible")
                if res == self.solver.ABNORMAL:
                    display("Something strange in the problem")
                if res == self.solver.NOT_SOLVED:
                    display("Problem could not be solved for some reason")            
        self.objectiveRanges = {objName: (lb[objName],ub[objName]) for objName in self.objectiveTypes.keys()}           


    def defineEpsilonConstraint(self,**kwargs):
        try:
            for objName in self.objectiveTypes.keys():
                self.epsilonConstraints[objName].SetCoefficient(self.objective[objName],1)
        except AttributeError:
            self.epsilonConstraints = {
                objName:self.solver.Constraint(-self.solver.infinity(),self.solver.infinity(),"epsilonConstraintFor"+objName)
                for objName in self.objectiveTypes.keys()
            }
            for objName in self.objectiveTypes.keys():
                self.epsilonConstraints[objName].SetCoefficient(self.objective[objName],1)
        epsilonValues = kwargs
        for objName in epsilonValues.keys():
            if self.objectiveTypes[objName][2] == "max":
                self.epsilonConstraints[objName].SetLb(epsilonValues[objName])
            elif self.objectiveTypes[objName][2] == "min":
                self.epsilonConstraints[objName].SetUb(epsilonValues[objName])

    def defineReferencePointAndSolve(self,**kwargs):
        display("Starting problem solving at "+str(datetime.now()))
        self.solutionCounter +=1
        referencePoint = kwargs
        for objName in self.objectiveTypes.keys():
            self.maxDummyConstraints[objName].SetCoefficient(self.maxDummy,1)
            if self.objectiveTypes[objName][2] == "max":
                self.maxDummyConstraints[objName].SetCoefficient(self.objective[objName],-1/(self.objectiveRanges[objName][1]-self.objectiveRanges[objName][0]))
                self.maxDummyConstraints[objName].SetUb(-referencePoint[objName]/(self.objectiveRanges[objName][1]-self.objectiveRanges[objName][0]))
                self.objectiveFunction.SetCoefficient(self.objective[objName],10**(-6)/(self.objectiveRanges[objName][1]-self.objectiveRanges[objName][0]))
            elif self.objectiveTypes[objName][2] == "min":
                self.maxDummyConstraints[objName].SetCoefficient(self.objective[objName],1/(self.objectiveRanges[objName][1]-self.objectiveRanges[objName][0]))
                self.maxDummyConstraints[objName].SetUb(referencePoint[objName]/(self.objectiveRanges[objName][1]-self.objectiveRanges[objName][0]))
                self.objectiveFunction.SetCoefficient(self.objective[objName],-10**(-6)/(self.objectiveRanges[objName][1]-self.objectiveRanges[objName][0]))

        self.objectiveFunction.SetCoefficient(self.maxDummy,1)
        if self.debug:
            problem = self.solver.ExportModelAsLpFormat(obfuscated=False)
            print(problem,file=open("problem.lp","w"))
            display("Problem exported at "+str(datetime.now()))
        now = datetime.now()
        res = self.solver.Solve()
        time = datetime.now() - now
        display("Problem solved at "+str(datetime.now()))
        self.solutionTimeStamp = str(now).replace(":"," ")
        if res == self.solver.OPTIMAL:
            for i,objName in enumerate(self.objectiveTypes.keys()):
                #Try to set the value of the slider if it exists
                try:
                    self.imRef.children[i].value = self.objective[objName].solution_value()
                except:
                    pass
            display("Found an optimal solution in "+str(time.seconds)+" seconds")
            display ({self.objectiveTypes[objName][0]:self.objective[objName].solution_value() for objName in self.objectiveTypes.keys()})
            display("Solution printed at "+str(datetime.now()))
            return {objName:self.objective[objName].solution_value() for objName in self.objectiveTypes.keys()}
        else:
            display("Could not solve")
            if res == self.solver.FIXED_VALUE:
                display("Objective value fixed")
            if res == self.solver.INFEASIBLE:
                display("Problem is infeasible")
            if res == self.solver.ABNORMAL:
                display("Something abnormal in the problem")
            if res == self.solver.NOT_SOLVED:
                display("Problem could not be solved for some reason")      

    def enableAndDisableConstraints(self,**kwargs):
        enabledConstraints = kwargs
        for constraintName in self.constraints.keys():
            if self.constraintTypes[constraintName][0] == "Allowed regimes":
                for regime in self.regimes:
                    if regime not in self.constraintTypes[constraintName][2]:
                        for standId in self.standIds:
                            if (standId,regime) in self.regimesDecision.keys() and self.data.loc[(standId,self.years[0],regime),self.constraintTypes[constraintName][3]] == 1:
                                self.constraints[constraintName][(standId,regime)].SetUb(1-(enabledConstraints[constraintName]))
            if self.constraintTypes[constraintName][0] == "Species reduction":
                periodNo = self.constraintTypes[constraintName][3]
                for i,year in enumerate(self.years):
                    if i >= periodNo:
                        self.constraints[constraintName][year].SetLb((-1+enabledConstraints[constraintName])*1e10)

    def printSolution(self,_):
        import os
        if not os.path.isdir("./results"):
            os.mkdir("./results")
        with open("./results/objectiveValues"+str(self.solutionCounter)+".csv","w") as file:
            delim = ""
            for objName in self.objectiveTypes.keys():
                file.write(delim+objName)
                delim = ","
            file.write("\n")
            delim = ""
            for objName in self.objectiveTypes.keys():
                file.write(delim+str(self.objective[objName].solution_value()))
                delim = ","
            file.write("\n")

    def showGUI(self,debug=False):
        self.debug=debug
        self.imEps = widgets.interactive(self.defineEpsilonConstraint, {'manual': True}, 
                 **{objName:self.objectiveRanges[objName] for objName in self.objectiveTypes.keys()}
                )
        self.imRef = widgets.interactive(self.defineReferencePointAndSolve, {'manual': True}, 
                **{objName:self.objectiveRanges[objName] for objName in self.objectiveTypes.keys()}
                )
        
        self.imConst = widgets.interactive(self.enableAndDisableConstraints, {'manual':True},
                        **{constraintName:False for constraintName in self.constraints.keys()})
        for i,constraintName in enumerate(self.constraints.keys()):
            self.imConst.children[i].description = self.constraintTypes[constraintName][1]
        for i,objName in enumerate(self.objectiveTypes.keys()):
            self.imEps.children[i].layout.width = "95%"
            self.imEps.children[i].description = self.objectiveTypes[objName][0]
            if self.objectiveTypes[objName][2] == "max":
                self.imEps.children[i].value = self.objectiveRanges[objName][0]
            elif self.objectiveTypes[objName][2] == "min":
                self.imEps.children[i].value = self.objectiveRanges[objName][1]
            self.imRef.children[i].layout.width = "95%"
            self.imRef.children[i].description = self.objectiveTypes[objName][0]
            self.imEps.children[i].step=0.01*(self.objectiveRanges[objName][1]-self.objectiveRanges[objName][0])
            self.imRef.children[i].step=0.01*(self.objectiveRanges[objName][1]-self.objectiveRanges[objName][0])
            self.imEps.children[i].readout_format ='e'
            self.imRef.children[i].readout_format ='e'
        self.imEps.children[-2].description = "Set epsilon constraints"
        self.imRef.children[-2].description = "OPTIMIZE"
        self.imConst.children[-2].description = "Change constraints"
        display(HTML('''<style>
            .widget-label { min-width: 60% !important; }
        </style>'''))

        display(HTML("<h2>Epsilon constraint values</h2>"))
        display(self.imEps)
        display(HTML("<h2>Reference point</h2>"))
        display(self.imRef)
        display(HTML("<h2>Enabled constraints</h2>"))
        display(self.imConst)
        self.printSolutionButton = widgets.Button(description='Print solution')
        self.printSolutionButton.on_click(self.printSolution)
        display(self.printSolutionButton)

