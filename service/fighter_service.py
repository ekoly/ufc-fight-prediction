from collections import defaultdict

import numpy as np
import pandas as pd

import category_encoders as ce
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline

import shap
import pickle
import re
import tarfile


class FighterService:


    def __init__(self):

        self.__fighters_df = pd.read_csv("csv/fighters.csv")
        self.__fighters = tuple(set(self.__fighters_df["fighter"]))

        self.__weight_to_fighters = defaultdict(list)
        for f, w in zip(self.__fighters_df["fighter"], self.__fighters_df["weight_class"]):
            self.__weight_to_fighters[w].append(f)

        sherdog_df = pd.read_csv("csv/ALL UFC FIGHTERS 2_23_2016 SHERDOG.COM - Sheet1.csv")
        sherdog_fighters = list(sherdog_df["name"])
        sherdog_nicks = list(sherdog_df["nick"])
        self.__fighters_to_nicks = {f: n for f, n in zip(sherdog_fighters, sherdog_nicks)}


        t = tarfile.open("pickles/pickles.tar.gz", "r:gz")

        with t.extractfile("pickles/feature_to_name.pickle") as f:
            self.__feature_to_name = pickle.load(f)

        with t.extractfile("pickles/pipeline.pickle") as f:
            self.__pipeline = pickle.load(f)

        self.__explainer = shap.TreeExplainer(self.__pipeline.named_steps["randomforestclassifier"])

        with t.extractfile("pickles/features.pickle") as f:
            self.__features = pickle.load(f)

        prefix_re = re.compile(r".*(_opponent)|(_ratio)$")

        fighters_individual_df = self.__fighters_df[[col for col in self.__fighters_df.columns.drop(["is_winner"]) if not prefix_re.match(col)]]
        self.__latest_fights = fighters_individual_df.sort_values(by="date").groupby("fighter").tail(1)

        self.__fighters_to_reach = {
                f: (str(r) + " cms") if r != np.NaN else "-"
                for f, r in zip(
                    self.__latest_fights["fighter"],
                    self.__latest_fights["Reach_cms"]
                )
        }

        self.__fighters_to_height = {
                f: (str(h) + " cms") if h != np.NaN else "-"
                for f, h in zip(
                    self.__latest_fights["fighter"],
                    self.__latest_fights["Height_cms"]
                )
        }

        self.__fighters_to_wins = {
                f: str(int(w)) if w != np.NaN else "-"
                for f, w in zip(
                    self.__latest_fights["fighter"],
                    self.__latest_fights["wins"]
                )
        }

        self.__fighters_to_losses = {
                f: str(int(l)) if l != np.NaN else "-"
                for f, l in zip(
                    self.__latest_fights["fighter"],
                    self.__latest_fights["losses"]
                )
        }


        # processing
        self.__fighters_df["Reach_cms"] = self.__fighters_df["Reach_cms"].replace({
            np.NaN: self.__fighters_df["Reach_cms"].median(skipna=True)
        })

        self.__fighters_df["Height_cms"] = self.__fighters_df["Height_cms"].replace({
            np.NaN: self.__fighters_df["Height_cms"].median(skipna=True)
        })



    def getNickname(self, fighter):
        """
            Returns the nickname of the fighter, or an empty string if none found.

            @type fighter: str
            @rtype: str
        """

        if fighter not in self.__fighters_to_nicks:
            return ""

        nick = self.__fighters_to_nicks[fighter]
        if nick in (np.NaN, "nan"):
            return ""

        return nick


    def getReach(self, fighter):
        """
            Returns the reach of the fighter, or "-" if none found.

            @type fighter: str
            @rtype: str
        """

        if fighter not in self.__fighters_to_reach:
            return "-"

        res = self.__fighters_to_reach[fighter].strip()

        if res in (None, np.NaN, "nan", "nan cms"):
            return "-"

        return res


    def getHeight(self, fighter):
        """
            Returns the height of the fighter, or "-" if none found.

            @type fighter: str
            @rtype: str
        """

        if fighter not in self.__fighters_to_height:
            return "-"

        res = self.__fighters_to_height[fighter].strip()

        if res in (None, np.NaN, "nan", "nan cms"):
            return "-"

        return res


    def getWins(self, fighter):
        """
            Returns the number of wins of the fighter, or "-" if none found.

            @type fighter: str
            @rtype: str
        """

        if fighter not in self.__fighters_to_wins:
            return "-"

        return self.__fighters_to_wins[fighter]


    def getLosses(self, fighter):
        """
            Returns the number of losses of the fighter, or "-" if none found.

            @type fighter: str
            @rtype: str
        """

        if fighter not in self.__fighters_to_losses:
            return "-"

        return self.__fighters_to_losses[fighter]


    def getAllFighters(self, weight_class=None):
        """
            Returns a list of the names of all fighters, or the subset
            of fighters who have fought in `weight_class`.

            @rtype: Tuple[str]
        """

        if not weight_class:
            return self.__fighters
        
        return tuple(
            self.__weight_to_fighters[weight_class]
        )


    def getWeightClasses(self):
        """
            Returns a list of all weight classes, by label and value.

            @rtype: Tuple[str, str]
        """

        return (
            ('Heavyweight', 'Heavyweight',),
            ('Light Heavyweight (205 lbs.)', 'Light Heavyweight',),
            ('Middleweight (185 lbs.)', 'Middleweight',),
            ('Welterweight (170 lbs.)', 'Welterweight',),
            ('Lightweight (155 lbs.)', 'Lightweight',),
            ('Featherweight (145 lbs.)', 'Featherweight',),
            ('Bantamweight (135 lbs.)', 'Bantamweight',),
            ('Flyweight (125 lbs.)', 'Flyweight',),
            ("Women's Featherweight (145 lbs.)", "Women's Featherweight",),
            ("Women's Bantamweight (135 lbs.)", "Women's Bantamweight",),
            ("Women's Flyweight (125 lbs.)", "Women's Flyweight",),
            ("Women's Strawweight (115 lbs.)", "Women's Strawweight",),
            ('Open Weight', ""),
        )


    def getFightersDF(self):
        """
            Returns the fighters dataframe.

            @rtype: pd.DataFrame
        """
        return self.__fighters_df


    def doPrediction(self, red_fighter, blue_fighter):
        """
            Given the names of two fighters, predicts which fighter would win.

            @type red_fighter: str
            @type blue_fighter: str

            @rtype: tuple
                - float of the percentage confidence of the prediction
                - str of the name of the winner
                - list of the names of the most significant features
                - list of the names of the most signficant counterargument features
        """

        if red_fighter and not blue_fighter:
            return 100.0, red_fighter, [], []

        if not red_fighter and blue_fighter:
            return 100.0, blue_fighter, [], []

        if not red_fighter and not blue_fighter:
            return 100.0, "-", [], []

        if red_fighter == blue_fighter:
            return 100.0, red_fighter, [], []

        bout = self.__makeBoutDf(red_fighter, blue_fighter)
        if bout is None:
            return 100.0, "-", [], []

        probas, shaps = self.__scoreBout(bout)

        red_fighter_prob = (probas.iloc[0]["True"] + probas.iloc[1]["False"])/2
        blue_fighter_prob = (probas.iloc[0]["False"] + probas.iloc[1]["True"])/2

        print(red_fighter_prob, "+", blue_fighter_prob, "=", red_fighter_prob+blue_fighter_prob)

        if red_fighter_prob > blue_fighter_prob:
            shap_values = shaps[True].iloc[0]
            winner_prob = red_fighter_prob
            winner = red_fighter

        else:
            shap_values = shaps[True].iloc[1]
            winner_prob = blue_fighter_prob
            winner = blue_fighter

        shap_values = shap_values.sort_values()
        neg_shaps = [
            self.__feature_to_name[s].strip() if s in self.__feature_to_name else ""
            for s in shap_values.index[:3]
        ]
        pos_shaps = [
            self.__feature_to_name[s].strip() if s in self.__feature_to_name else ""
            for s in shap_values.index[-3:]
        ]

        return winner_prob*100, winner, pos_shaps, neg_shaps


    def __getByFighter(self, fighter_name):
        return self.__latest_fights[self.__latest_fights["fighter"] == fighter_name].copy()


    def __makeBoutDf(self, fighter1, fighter2):

        fighter1_df = self.__getByFighter(fighter1)
        fighter2_df = self.__getByFighter(fighter2)

        if len(fighter1_df) != 1 or len(fighter2_df) != 1:
            return None

        fighter1_df["temp_id_"] = fighter2_df["temp_id_"] = np.random.randint(2**31)
        fighter1_df, fighter2_df = (
            pd.merge(fighter1_df, fighter2_df, on="temp_id_", suffixes=("", "_opponent")),
            pd.merge(fighter2_df, fighter1_df, on="temp_id_", suffixes=("", "_opponent")),
        )

        fight_df = pd.concat([fighter1_df, fighter2_df])

        for col in [col for col in fight_df.select_dtypes(include="number").columns if col.endswith("_opponent")]:

            col2 = col
            col1 = col[:-9]

            fight_df[col1 + "_ratio"] = (fight_df[col1] + 1) / (fight_df[col2] + 1)

        fight_df["stance_config"] = fight_df["Stance"] + "-" + fight_df["Stance_opponent"]

        return fight_df.drop(columns=["temp_id_"])


    def __scoreBout(self, bout):

        bout_t = bout[self.__features]

        _, ohe = self.__pipeline.steps[0]
        bout_ohe = ohe.transform(bout_t)

        _, si = self.__pipeline.steps[1]
        bout_si = si.transform(bout_ohe)

        proba_values = self.__pipeline["randomforestclassifier"].predict_proba(bout_si)
        
        probas = pd.DataFrame(data=proba_values, columns=[str(x) for x in self.__pipeline.classes_])

        print("FighterService__scoreBout():")
        print("\tprobas.shape:", probas.shape)
        print("\tprobas:")
        print(probas)

        shap_values = self.__explainer.shap_values(bout_si, check_additivity=False)
        print("\tshap_values:", len(shap_values), shap_values)

        shaps = {
            self.__pipeline.classes_[0]: pd.DataFrame(data=shap_values[0], columns=bout_ohe.columns),
            self.__pipeline.classes_[1]: pd.DataFrame(data=shap_values[1], columns=bout_ohe.columns),
        }

        return probas, shaps



fighter_service = FighterService()
