import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import backtrader as bt
import quandl
import os
import statsmodels.api as sm
import scipy.stats as scs
import pmdarima as pm

from datetime import date, datetime
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing, Holt
from statsmodels.tsa.arima_model import ARIMA
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import adfuller, kpss
from fbprophet import Prophet
from pmdarima.arima import ndiffs, nsdiffs
from dotenv import load_dotenv
from icecream import ic

plt.style.use("seaborn-colorblind")
plt.rcParams["figure.figsize"] = [12, 8]
plt.rcParams["figure.dpi"] = 300
plt.set_cmap("cubehelix")
sns.set_palette("cubehelix")
warnings.simplefilter(action="ignore", category=FutureWarning)

COLORS = [plt.cm.cubehelix(x) for x in [0.1, 0.3, 0.5, 0.7, 0.9]]

load_dotenv(verbose=True)
quandl.ApiConfig.api_key = os.getenv("Quandl")


def adf_test(x):
    """
    Function for performing the Augmented Dickey-Fuller test for stationarity
    Null Hypothesis: time series is not stationary
    Alternate Hypothesis: time series is stationary
    Parameters
    ----------
    x : pd.Series / np.array
        The time series to be checked for stationarity
    Returns
    -------
    results: pd.DataFrame
        A DataFrame with the ADF test's results
    """

    indices = ["Test Statistic", "p-value", "# of Lags Used", "# of Observations Used"]
    adf_test = adfuller(x, autolag="AIC")
    results = pd.Series(adf_test[0:4], index=indices)
    for key, value in adf_test[4].items():
        results[f"Critical Value ({key})"] = value
    return results


def kpss_test(x, h0_type="c"):
    """
    Function for performing the Kwiatkowski-Phillips-Schmidt-Shin test for stationarity
    Null Hypothesis: time series is stationary
    Alternate Hypothesis: time series is not stationary
    Parameters
    ----------
    x: pd.Series / np.array
        The time series to be checked for stationarity
    h0_type: str{'c', 'ct'}
        Indicates the null hypothesis of the KPSS test:
            * 'c': The data is stationary around a constant(default)
            * 'ct': The data is stationary around a trend
    Returns
    -------
    results: pd.DataFrame
        A DataFrame with the KPSS test's results
    """

    indices = ["Test Statistic", "p-value", "# of Lags"]
    kpss_test = kpss(x, regression=h0_type, nlags="auto")
    results = pd.Series(kpss_test[0:3], index=indices)
    for key, value in kpss_test[3].items():
        results[f"Critical Value ({key})"] = value
    return results


def test_autocorrelation(x, n_lags=40, alpha=0.05, h0_type="c"):
    """
    Function for testing the stationarity of a series by using:
    * the ADF test
    * the KPSS test
    * ACF/PACF plots
    Parameters
    ----------
    x: pd.Series / np.array
        The time series to be checked for stationarity
    n_lags : int
        The number of lags for the ACF/PACF plots
    alpha : float
        Significance level for the ACF/PACF plots
    h0_type: str{'c', 'ct'}
        Indicates the null hypothesis of the KPSS test:
            * 'c': The data is stationary around a constant(default)
            * 'ct': The data is stationary around a trend
    Returns
    -------
    fig : matplotlib.figure.Figure
        Figure containing the ACF/PACF plot
    """

    adf_results = adf_test(x)
    kpss_results = kpss_test(x, h0_type=h0_type)
    print(
        "ADF test statistic: {:.2f} (p-val: {:.2f})".format(
            adf_results["Test Statistic"], adf_results["p-value"]
        )
    )
    print(
        "KPSS test statistic: {:.2f} (p-val: {:.2f})".format(
            kpss_results["Test Statistic"], kpss_results["p-value"]
        )
    )
    fig, ax = plt.subplots(2, figsize=(8, 4))
    plot_acf(x, ax=ax[0], lags=n_lags, alpha=alpha)
    plot_pacf(x, ax=ax[1], lags=n_lags, alpha=alpha)
    return fig


def decompose_time_series(data):
    df = data.copy()
    df = df[["close"]].rename(columns={"close": "price"})
    df = df.resample("M").last()
    ic(f"Shape of DataFrame: {df.shape}")
    ic(df.head())

    df["rolling_mean"] = df.price.rolling(window=12).mean()
    df["rolling_std"] = df.price.rolling(window=12).std()
    df.plot(title="Stock Price")
    plt.tight_layout()
    plt.savefig("images/ch3_im1.png", format="png", dpi=300)

    # 4. Carry out seasonal decomposition using the multiplicative model:
    decomposition_results = seasonal_decompose(df.price, model="multiplicative")
    decomposition_results.plot().suptitle("Multiplicative Decomposition", fontsize=14)
    plt.tight_layout()
    plt.savefig("images/ch3_im2.png")
    plt.close()


def decompose_with_prophet(data):
    df = data.copy()
    df = df[["close"]].reset_index(drop=False)
    ic(df.head())
    df.rename(columns={"date": "ds", "close": "y"}, inplace=True)

    train_indices = df.ds.apply(lambda x: x.year).values < 2020
    ic(train_indices)
    df_train = df.loc[train_indices].dropna()
    df_test = df.loc[~train_indices].reset_index(drop=True)
    ic(df_train)
    ic(df_test.tail())

    model_prophet = Prophet(seasonality_mode="additive", daily_seasonality=False)
    model_prophet.add_seasonality(name="monthly", period=30.5, fourier_order=5)
    model_prophet.fit(df_train)

    # 5. Forecast the gold prices 1 year ahead and plot the results:
    df_future = model_prophet.make_future_dataframe(periods=720)
    ic(df_future.tail())
    df_pred = model_prophet.predict(df_future)
    ic(df_pred[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail())
    model_prophet.plot(df_pred)
    plt.tight_layout()
    plt.savefig("images/ch3_im3.png")

    # 6. Inspect the decomposition of the time series:
    model_prophet.plot_components(df_pred)
    plt.tight_layout()
    plt.savefig("images/ch3_im4.png")
    plt.close()

    # 1. Merge the test set with the forecasts:
    selected_columns = ["ds", "yhat_lower", "yhat_upper", "yhat"]
    df_pred = df_pred.loc[:, selected_columns].reset_index(drop=True)
    df_test = df_test.merge(df_pred, on=["ds"], how="left")
    df_test.ds = pd.to_datetime(df_test.ds)
    df_test.set_index("ds", inplace=True)

    _, ax = plt.subplots(1, 1)
    ax = sns.lineplot(data=df_test[["y", "yhat_lower", "yhat_upper", "yhat"]])
    ax.fill_between(df_test.index, df_test.yhat_lower, df_test.yhat_upper, alpha=0.3)
    ax.set(title="Stock Price - actual vs. predicted", xlabel="Date", ylabel="Price (won)")
    plt.tight_layout()
    plt.savefig("images/ch3_im5.png")
    plt.close()


def testing_stationary(data):
    df = data.copy()
    df = df[["close"]].rename(columns={"close": "price"})
    df = df.resample("M").last()

    ic(adf_test(df.price))
    ic(kpss_test(df.price))

    N_LAGS = 40
    SIGNIFICANCE_LEVEL = 0.05

    _, ax = plt.subplots(2, 1)
    plot_acf(df.price, ax=ax[0], lags=N_LAGS, alpha=SIGNIFICANCE_LEVEL)
    plot_pacf(df.price, ax=ax[1], lags=N_LAGS, alpha=SIGNIFICANCE_LEVEL)
    plt.tight_layout()
    plt.savefig("images/ch3_im8.png")
    plt.close()

    # 3. Deflate the series using natural logarithm and plot it together with the rolling metrics:
    WINDOW = 12
    selected_columns = ["price_log", "rolling_mean_log", "rolling_std_log"]
    df["price_log"] = np.log(df.price)
    df["rolling_mean_log"] = df.price_log.rolling(WINDOW).mean()
    df["rolling_std_log"] = df.price_log.rolling(WINDOW).std()

    df[selected_columns].plot(title="Stock Price (logged)")
    plt.tight_layout()
    plt.savefig("images/ch3_im10.png")
    plt.close()

    # 4. Use the `test_autocorrelation` (helper function for this chapter)
    # to investigate if the series became stationary:
    plt.clf()
    test_autocorrelation(df.price_log)
    plt.tight_layout()
    plt.savefig("images/ch3_im11.png")
    plt.close()

    # 5. Apply differencing to the series and plot the results:
    selected_columns = ["price_log_diff", "roll_mean_log_diff", "roll_std_log_diff"]
    df["price_log_diff"] = df.price_log.diff(1)
    df["roll_mean_log_diff"] = df.price_log_diff.rolling(WINDOW).mean()
    df["roll_std_log_diff"] = df.price_log_diff.rolling(WINDOW).std()

    plt.clf()
    df[selected_columns].plot(title="Gold Price (1st differences)")
    plt.tight_layout()
    plt.savefig("images/ch3_im12.png")

    # 6. Test if the series became stationary:
    test_autocorrelation(df.price_log_diff.dropna())
    plt.tight_layout()
    plt.savefig("images/ch3_im13.png")

    ic(f"Suggested # of differences (ADF): {ndiffs(df.price, test='adf')}")
    ic(f"Suggested # of differences (KPSS): {ndiffs(df.price, test='kpss')}")
    ic(f"Suggested # of differences (PP): {ndiffs(df.price, test='pp')}")
    ic(f"Suggested # of differences (OSCB): {nsdiffs(df.price, m=12, test='ocsb')}")
    ic(f"Suggested # of differences (CH): {nsdiffs(df.price, m=12, test='ch')}")


def exponential_smoothing():
    src_data = "data/yf_google.pkl"
    start = datetime(2000, 1, 1)
    end = datetime(2020, 12, 31)
    try:
        goog = pd.read_pickle(src_data)
        print("data reading from file...")
    except FileNotFoundError:
        goog = yf.download("GOOG", start=start, end=end, adjusted=True)
        goog.to_pickle(src_data)
    df = goog.copy()["2010-1":"2018-12"]
    ic(f"Downloaded {df.shape[0]} rows of data.")
    goog = df.resample("M").last().rename(columns={"Adj Close": "adj_close"}).adj_close

    train_indices = goog.index.year < 2018
    goog_train = goog[train_indices]
    goog_test = goog[~train_indices]
    test_length = len(goog_test)

    plt.clf()
    goog.plot(title="Google's Stock Price")
    plt.tight_layout()
    plt.savefig("images/ch3_im14.png")

    # 6. Fit 3 Simple Exponential Smoothing models and create forecasts:
    ses_1 = SimpleExpSmoothing(goog_train, initialization_method="estimated").fit(
        smoothing_level=0.2
    )
    ses_forecast_1 = ses_1.forecast(steps=test_length)
    ses_2 = SimpleExpSmoothing(goog_train, initialization_method="estimated").fit(
        smoothing_level=0.5
    )
    ses_forecast_2 = ses_2.forecast(steps=test_length)
    ses_3 = SimpleExpSmoothing(goog_train, initialization_method="estimated").fit(
        smoothing_level=None
    )
    alpha = ses_3.model.params["smoothing_level"]
    ses_forecast_3 = ses_3.forecast(steps=test_length)

    # 7. Plot the original prices together with the models' results:
    plt.clf()
    goog.plot(color=COLORS[0], title="Simple Exponential Smoothing", label="Actual", legend=True)
    ses_forecast_1.plot(color=COLORS[1], legend=True, label=r"$\alpha=0.2$")
    ses_1.fittedvalues.plot(color=COLORS[1])
    ses_forecast_2.plot(color=COLORS[2], legend=True, label=r"$\alpha=0.5$")
    ses_2.fittedvalues.plot(color=COLORS[2])
    ses_forecast_3.plot(color=COLORS[3], legend=True, label=r"$\alpha={0:.4f}$".format(alpha))
    ses_3.fittedvalues.plot(color=COLORS[3])
    plt.tight_layout()
    plt.savefig("images/ch3_im15.png")
    plt.close()

    # Holt's model with linear trend
    hs_1 = Holt(goog_train).fit()
    hs_forecast_1 = hs_1.forecast(test_length)
    # Holt's model with exponential trend
    hs_2 = Holt(goog_train, exponential=True, damped=False).fit()
    # equivalent to ExponentialSmoothing(goog_train, trend='mul').fit()
    hs_forecast_2 = hs_2.forecast(test_length)
    # Holt's model with exponential trend and damping
    hs_3 = Holt(goog_train, exponential=True, damped=True).fit(damping_slope=0.99)
    hs_forecast_3 = hs_3.forecast(test_length)

    # 9. Plot the original prices together with the models' results:
    plt.clf()
    goog.plot(color=COLORS[0], title="Holt's Smoothing models", label="Actual", legend=True)
    hs_1.fittedvalues.plot(color=COLORS[1])
    hs_forecast_1.plot(color=COLORS[1], legend=True, label="Linear trend")
    hs_2.fittedvalues.plot(color=COLORS[2])
    hs_forecast_2.plot(color=COLORS[2], legend=True, label="Exponential trend")
    hs_3.fittedvalues.plot(color=COLORS[3])
    hs_forecast_3.plot(color=COLORS[3], legend=True, label="Exponential trend (damped)")
    plt.tight_layout()
    plt.savefig("images/ch3_im16.png")

    SEASONAL_PERIODS = 12
    # Holt-Winter's model with exponential trend
    hw_1 = ExponentialSmoothing(
        goog_train,
        trend="mul",
        seasonal="add",
        seasonal_periods=SEASONAL_PERIODS,
        damped=False,
        initialization_method="estimated",
    ).fit()
    hw_forecast_1 = hw_1.forecast(test_length)
    # Holt-Winter's model with exponential trend and damping
    hw_2 = ExponentialSmoothing(
        goog_train,
        trend="mul",
        seasonal="add",
        seasonal_periods=SEASONAL_PERIODS,
        damped=True,
        initialization_method="estimated",
    ).fit()
    hw_forecast_2 = hw_2.forecast(test_length)

    plt.clf()
    goog.plot(
        color=COLORS[0], title="Holt-Winter's Seasonal Smoothing", label="Actual", legend=True
    )
    hw_1.fittedvalues.plot(color=COLORS[1])
    hw_forecast_1.plot(color=COLORS[1], legend=True, label="Seasonal Smoothing")
    phi = hw_2.model.params["damping_trend"]
    plot_label = f"Seasonal Smoothing (damped with $\phi={phi:.4f}$)"
    hw_2.fittedvalues.plot(color=COLORS[2])
    hw_forecast_2.plot(color=COLORS[2], legend=True, label=plot_label)
    plt.tight_layout()
    plt.savefig("images/ch3_im17.png")


def arima_models(data):
    df = data.copy().sort_index()["2010-1":"2020-12"][["close"]]
    df = df.resample("W").last().dropna().to_period("W")
    df_diff = df.diff(periods=1).dropna()
    df.info()
    df_diff.info()

    _, ax = plt.subplots(2, sharex=True)
    df.plot(title="stock price", ax=ax[0])
    df_diff.plot(ax=ax[1], title="First Differences")
    plt.tight_layout()
    plt.savefig("images/ch3_im18.png")
    test_autocorrelation(df_diff)
    plt.tight_layout()
    plt.savefig("images/ch3_im19.png")

    arima = ARIMA(df, order=(2, 1, 1)).fit(disp=0)
    ic(arima.summary())

    def arima_diagnostics(resids, n_lags=40):
        """
        Function for diagnosing the fit of an ARIMA model by investigating the residuals.
        Parameters
        ----------
        resids : np.array
            An array containing the residuals of a fitted model
        n_lags : int
            Number of lags for autocorrelation plot
        Returns
        -------
        fig : matplotlib.figure.Figure
            Created figure
        """
        # create placeholder subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2)
        r = resids
        resids = (r - np.nanmean(r)) / np.nanstd(r)
        resids_nonmissing = resids[~(np.isnan(resids))]
        # residuals over time
        sns.lineplot(x=np.arange(len(resids)), y=resids, ax=ax1)
        ax1.set_title("Standardized residuals")
        # distribution of residuals
        x_lim = (-1.96 * 2, 1.96 * 2)
        r_range = np.linspace(x_lim[0], x_lim[1])
        norm_pdf = scs.norm.pdf(r_range)

        sns.distplot(resids_nonmissing, hist=True, kde=True, norm_hist=True, ax=ax2)
        ax2.plot(r_range, norm_pdf, "g", lw=2, label="N(0,1)")
        ax2.set_title("Distribution of standardized residuals")
        ax2.set_xlim(x_lim)
        ax2.legend()
        sm.qqplot(resids_nonmissing, marker="o", line="s", ax=ax3)
        ax3.set_title("Q-Q plot")
        plot_acf(resids, ax=ax4, lags=n_lags, alpha=0.05)
        ax4.set_title("ACF plot")
        return fig

    arima_diagnostics(arima.resid, 40)
    plt.tight_layout()
    plt.savefig("images/ch3_im21.png")

    # 8. Apply the Ljung-Box's test for no autocorrelation in the residuals and plot the results:
    ljung_box_results = acorr_ljungbox(arima.resid)

    _, ax = plt.subplots(1, figsize=[16, 5])
    sns.scatterplot(x=range(len(ljung_box_results[1])), y=ljung_box_results[1], ax=ax)
    ax.axhline(0.05, ls="--", c="r")
    ax.set(title="Ljung-Box test's results", xlabel="Lag", ylabel="p-value")
    plt.tight_layout()
    plt.savefig("images/ch3_im22.png")

    auto_arima = pm.auto_arima(df, error_action="ignore", suppress_warnings=True, seasonal=False)
    auto_arima.summary()

    auto_arima = pm.auto_arima(
        df,
        error_action="ignore",
        suppress_warnings=True,
        seasonal=False,
        stepwise=False,
        approximation=False,
        n_jobs=-1,
    )
    ic(auto_arima.summary())

    ## Forecasting using ARIMA class models
    df = data.copy().sort_index()["2021-1":"2021-8"][["close"]]
    test = df.resample("W").last().dropna()

    n_forecasts = len(test)
    arima_pred = arima.forecast(n_forecasts)
    arima_pred = [
        pd.DataFrame(arima_pred[0], columns=["prediction"]),
        pd.DataFrame(arima_pred[2], columns=["ci_lower", "ci_upper"]),
    ]
    arima_pred = pd.concat(arima_pred, axis=1).set_index(test.index)
    auto_arima_pred = auto_arima.predict(n_periods=n_forecasts, return_conf_int=True, alpha=0.05)
    auto_arima_pred = [
        pd.DataFrame(auto_arima_pred[0], columns=["prediction"]),
        pd.DataFrame(auto_arima_pred[1], columns=["ci_lower", "ci_upper"]),
    ]
    auto_arima_pred = pd.concat(auto_arima_pred, axis=1).set_index(test.index)

    df = pd.concat([test, arima_pred, auto_arima_pred], axis=1, join="inner")
    df.plot(
        kind="line",
        title="stock price - actual vs. predicted",
        xlabel="Date",
        ylabel="Price (won)",
        figsize=(8, 6),
    )
    plt.tight_layout()
    plt.savefig("images/ch3_im24.png")

    _, ax = plt.subplots(1)
    ax = sns.lineplot(data=test, color=COLORS[0], label="Actual")
    ax.plot(data=arima_pred.prediction, label="ARIMA(2,1,1)")
    ax.fill_between(
        arima_pred.index, arima_pred.ci_lower, arima_pred.ci_upper, alpha=0.3, facecolor=COLORS[4]
    )
    ax.plot(data=auto_arima_pred.prediction, color=COLORS[2], label="ARIMA(3,1,2)")
    ax.fill_between(
        auto_arima_pred.index,
        auto_arima_pred.ci_lower,
        auto_arima_pred.ci_upper,
        alpha=0.1,
        facecolor=COLORS[3],
    )
    ax.set(title="stock price - actual vs. predicted", xlabel="Date", ylabel="Price (won))")
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig("images/ch3_im25.png")


if __name__ == "__main__":
    df = pd.read_pickle("./data/stock1.pkl")
    data = df.loc["현대차"]
    data.set_index("date", inplace=True)
    data = data.sort_index()["2010-1":"2021-12"]
    data.info()

    # decompose_time_series(data)
    # decompose_with_prophet(data)
    # testing_stationary(data)
    # exponential_smoothing()
    arima_models(data)
