from collections import defaultdict
import random
import numpy as np
import pandas as pd
factors = [
    "momentum", "value", "quality", "growth",
    "defensive", "size", "liquidity"] # diversification factor - not a real factor, but can be used to push users towards more diversified strategies

def build_questionnaire(ans1, ans2, ans3, ans4, ans5, ans6, ans7):
    """
    Build questionnaire structure with user responses.
    ans are expected to be True/False/None (None for unanswered)
    """

    return [
        # Q1
        {
            "response": ans1,
            "weights_yes": {"size": -2, "defensive": +3, "quality": +3, "value": -1},
            "weights_no": {"size": +1, "defensive": -1, "quality": -1, "value": +3}
        },

        # Q2
        {
            "response": ans2,
            "weights_yes": {"size": -2, "momentum": +2, "defensive": -1},
            "weights_no": {"size": +1, "momentum": -2, "defensive": +1}
        },

        # Q3
        {
            "response": ans3,
            "weights_yes": {"defensive": +3, "quality": +2, "growth": -1, "liquidity": +2},
            "weights_no": {"defensive": -2, "quality": -1, "growth": +3, "momentum": +2, "liquidity": -2}
        },

        # Q4
        {
            "response": ans4,
            "weights_yes": {"value": +3, "quality": -2, "defensive": -3, "momentum": -3},
            "weights_no": {"value": -2, "quality": +3, "defensive": +2, "momentum": +2}
        },

        # Q5
        {
            "response": ans5,
            "weights_yes": {"size": -3, "quality": +2, "defensive": +3, "value": -2, "liquidity": +2},
            "weights_no": {"size": +3, "growth": +3, "quality": -2, "liquidity": -2}
        },

        # Q6
        {
            "response": ans6,
            "weights_yes": {"defensive": +3, "quality": +2, "momentum": -1, "value": +1, "liquidity": +3},
            "weights_no": {"defensive": -2, "growth": +2, "momentum": +2, "quality": +1, "liquidity": -1}
        },

        # Q7
        {
            "response": ans7,
            "weights_yes": {"quality": +3, "value": +2, "defensive": +2, "growth": -3},
            "weights_no": {"growth": +2, "momentum": +2, "quality": -3, "defensive": -2}
        },
    ]



def build_raw_user_weights(answers, all_factors=[
    "momentum", "value", "quality", "growth",
    "defensive", "size", "liquidity"]):
    """
    Builds raw (unnormalized) user preference weights.

    Parameters:
    ----------
    answers : list of dicts
        Each answer should look like:
        {
            "response": True/False,
            "weights_yes": {...},
            "weights_no": {...}
        }

    all_factors : list (optional)
        List of all factors to ensure they appear in output

    Returns:
    -------
    dict
        Raw accumulated weights (can be negative/positive, unbounded)
    """

    # ---------------------------------------
    # 1. Initialize
    # ---------------------------------------
    weights = defaultdict(float)

    if all_factors:
        for f in all_factors:
            weights[f] = 0.0

    # ---------------------------------------
    # 2. Accumulate answers
    # ---------------------------------------
    for q in answers:
        if q["response"] is None:
            continue  # skip unanswered questions
        selected_weights = q["weights_yes"] if q["response"] else q["weights_no"]

        for factor, value in selected_weights.items():
            weights[factor] += value

    # ---------------------------------------
    # 3. Convert to regular dict (clean output)
    # ---------------------------------------
    return dict(weights)




def questionnaire_to_weights(answers, factors=[
    "momentum", "value", "quality", "growth",
    "defensive", "size", "liquidity"]):
    """
    Converts questionnaire answers to normalized weights between 1 and 100

    Parameters:
    ----------
    answers : list of dicts
        Each answer should look like:
        {
            "response": True/False,
            "weights_yes": {...},
            "weights_no": {...}
        }

    factors : list
        List of all factors (e.g. ["momentum", "value", ...])

    Returns:
    -------
    dict
        Normalized weights between 1 and 100
    """

    # ---------------------------------------
    # 1. Build RAW weights
    # ---------------------------------------
    raw_weights = build_raw_user_weights(answers, factors)

    # ---------------------------------------
    # 2. Precomputed statistics (from simulation)
    # ---------------------------------------
    mu = {
        "momentum": 1.600,
        "value": 1.604,
        "quality": 2.793,
        "growth": 2.406,
        "defensive": 2.391,
        "size": -0.802,
        "liquidity": 0.795
    }

    sigma = {
        "momentum": 3.462,
        "value": 3.249,
        "quality": 4.610,
        "growth": 3.396,
        "defensive": 4.968,
        "size": 3.300,
        "liquidity": 3.123
    }

    # controls sensitivity per factor
    alpha = {
        "momentum": 1.0,
        "value": 1.0,
        "quality": 0.9,
        "growth": 1.0,
        "defensive": 0.9,
        "size": 1.2,
        "liquidity": 1.1
    }

    eps = 1e-6  # safety for division

    # ---------------------------------------
    # 3. Normalize using tanh
    # ---------------------------------------
    normalized_weights = {}

    for factor in factors:
        raw_val = raw_weights.get(factor, 0.0)

        # standardize
        z = (raw_val - mu[factor]) / (sigma[factor] + eps)

        # squash with tanh
        score = 50 + 40 * np.tanh(alpha[factor] * z)

        # hard bounds (extra safety)
        score = max(1, min(100, score))

        normalized_weights[factor] = round(score, 2)

    return normalized_weights



def build_user_strategy_final():
    pass

###########################    testing      ############################

def generate_random_user_weights(num_users=10**6):
    row_list = []
    for i in range(0,num_users):
        ans1 = random.choices([True, False, None], weights=[0.4, 0.4, 0.2])[0]
        ans2 = random.choices([True, False, None], weights=[0.4, 0.4, 0.2])[0]
        ans3 = random.choices([True, False, None], weights=[0.4, 0.4, 0.2])[0]
        ans4 = random.choices([True, False, None], weights=[0.4, 0.4, 0.2])[0]
        ans5 = random.choices([True, False, None], weights=[0.4, 0.4, 0.2])[0]
        ans6 = random.choices([True, False, None], weights=[0.4, 0.4, 0.2])[0]
        ans7 = random.choices([True, False, None], weights=[0.4, 0.4, 0.2])[0]

       

        new_row = questionnaire_to_weights(build_questionnaire(ans1, ans2, ans3, ans4, ans5, ans6, ans7), factors)
        row_list.append(new_row)
        
    df = pd.DataFrame(row_list)


    stats = df.describe().round(3)
    print(stats)
   




print(pd.DataFrame([questionnaire_to_weights(build_questionnaire(True, False, True, False, True, False, True))]))