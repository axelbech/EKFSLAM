# %% Imports
from typing import List, Optional

from scipy.io import loadmat
import numpy as np
import scipy.linalg as la

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import animation
from scipy.stats import chi2
import utils

try:
    from tqdm import tqdm
except ImportError as e:
    print(e)
    print("install tqdm to have progress bar")

    # def tqdm as dummy as it is not available
    def tqdm(*args, **kwargs):
        return args[0]

# %% plot config check and style setup


# to see your plot config
print(f"matplotlib backend: {matplotlib.get_backend()}")
print(f"matplotlib config file: {matplotlib.matplotlib_fname()}")
print(f"matplotlib config dir: {matplotlib.get_configdir()}")
plt.close("all")

# try to set separate window ploting
if "inline" in matplotlib.get_backend():
    print("Plotting is set to inline at the moment:", end=" ")

    if "ipykernel" in matplotlib.get_backend():
        print("backend is ipykernel (IPython?)")
        print("Trying to set backend to separate window:", end=" ")
        import IPython

        IPython.get_ipython().run_line_magic("matplotlib", "")
    else:
        print("unknown inline backend")

print("continuing with this plotting backend", end="\n\n\n")


# set styles
try:
    # installed with "pip install SciencePLots" (https://github.com/garrettj403/SciencePlots.git)
    # gives quite nice plots
    plt_styles = ["science", "grid", "bright", "no-latex"]
    plt.style.use(plt_styles)
    print(f"pyplot using style set {plt_styles}")
except Exception as e:
    print(e)
    print("setting grid and only grid and legend manually")
    plt.rcParams.update(
        {
            # setgrid
            "axes.grid": True,
            "grid.linestyle": ":",
            "grid.color": "k",
            "grid.alpha": 0.5,
            "grid.linewidth": 0.5,
            # Legend
            "legend.frameon": True,
            "legend.framealpha": 1.0,
            "legend.fancybox": True,
            "legend.numpoints": 1,
        }
    )



from EKFSLAM import EKFSLAM
from plotting import ellipse

# %% Load data
simSLAM_ws = loadmat("simulatedSLAM")

## NB: this is a MATLAB cell, so needs to "double index" to get out the measurements of a time step k:
#
# ex:
#
# z_k = z[k][0] # z_k is a (2, m_k) matrix with columns equal to the measurements of time step k
#
##
z = [zk.T for zk in simSLAM_ws["z"].ravel()]

landmarks = simSLAM_ws["landmarks"].T
odometry = simSLAM_ws["odometry"].T
poseGT = simSLAM_ws["poseGT"].T

K = len(z)
M = len(landmarks)
simSteps = 1000 # Max K=1000

# %% Initilize
Q = np.diag((np.array([0.2, 0.2, 0.01]))**2) # TODO
R = np.diag(np.array([0.1, 0.02])**2) # (0.04 * np.eye(2))**2 # TODO


doAsso = True

jointAlpha = 1e-6 #1e-5
individualAlpha = 1e-10#1e-10

JCBBalphas = np.array([jointAlpha, individualAlpha]) # TODO # first is for joint compatibility, second is individual
# these can have a large effect on runtime either through the number of landmarks created
# or by the size of the association search space.https://github.com/axelbech/EKFSLAM

slam = EKFSLAM(Q, R, do_asso=doAsso, alphas=JCBBalphas)

# allocate
eta_pred: List[Optional[np.ndarray]] = [None] * K
P_pred: List[Optional[np.ndarray]] = [None] * K
eta_hat: List[Optional[np.ndarray]] = [None] * K
P_hat: List[Optional[np.ndarray]] = [None] * K
a: List[Optional[np.ndarray]] = [None] * K
NIS = np.zeros(simSteps)
NISnorm = np.zeros(simSteps)
NISrange = np.zeros(simSteps)
NISbearing = np.zeros(simSteps)
NISrange_norm = np.zeros(simSteps)
NISbearing_norm = np.zeros(simSteps)
CI = np.zeros((simSteps, 2))
CI_1dim = np.zeros((simSteps, 2))
CInorm = np.zeros((simSteps, 2))
CI_1dim_norm = np.zeros((simSteps, 2))
NEESes = np.zeros((simSteps, 3))

# For consistency testing
alpha = 0.05

# init
eta_pred[0] = poseGT[0]  # we start at the correct position for reference
P_pred[0] = np.zeros((3, 3))  # we also say that we are 100% sure about that

# %% Set up plotting
# plotting

doAssoPlot = False
playMovie = False

if doAssoPlot:
    figAsso, axAsso = plt.subplots(num=1, clear=True)

# %% Run simulation
N = simSteps

print("starting sim (" + str(N) + " iterations)")

for k, z_k in tqdm(enumerate(z[:N])):
    eta_hat[k], P_hat[k], NIS[k], NISrange[k], NISbearing[k], a[k] = slam.update(eta_pred[k], P_pred[k], z_k) # TODO update

    if k < K - 1:
        eta_pred[k + 1], P_pred[k + 1] = slam.predict(eta_hat[k], P_hat[k], odometry[k]) # TODO predict

    assert (
        eta_hat[k].shape[0] == P_hat[k].shape[0]
    ), "dimensions of mean and covariance do not match"

    num_asso = np.count_nonzero(a[k] > -1)

    CI[k] = chi2.interval(1-alpha, 2 * num_asso)
    CI_1dim[k] = chi2.interval(1-alpha, num_asso)

    if num_asso > 0:
        NISnorm[k] = NIS[k] / (2 * num_asso)
        NISrange_norm[k] = NISrange[k] / num_asso
        NISbearing_norm[k] = NISbearing[k] / num_asso
        CInorm[k] = CI[k] / (2 * num_asso)
        CI_1dim_norm[k] = CI_1dim[k] / num_asso
    else:
        NISnorm[k] = 1
        CInorm[k].fill(1)
        NISrange_norm[k] = 1
        NISbearing_norm[k] = 1
        CI_1dim_norm[k].fill(1)

    NEESes[k] = slam.NEESes(eta_hat[k][:3], P_hat[k][:3,:3], poseGT[k])# TODO, use provided function slam.NEESes

    if doAssoPlot and k > 0:
        axAsso.clear()
        axAsso.grid()
        zpred = slam.h(eta_pred[k]).reshape(-1, 2)
        axAsso.scatter(z_k[:, 0], z_k[:, 1], label="z")
        axAsso.scatter(zpred[:, 0], zpred[:, 1], label="zpred")
        xcoords = np.block([[z_k[a[k] > -1, 0]], [zpred[a[k][a[k] > -1], 0]]]).T
        ycoords = np.block([[z_k[a[k] > -1, 1]], [zpred[a[k][a[k] > -1], 1]]]).T
        for x, y in zip(xcoords, ycoords):
            axAsso.plot(x, y, lw=3, c="r")
        axAsso.legend()
        axAsso.set_title(f"k = {k}, {np.count_nonzero(a[k] > -1)} associations")
        plt.draw()
        plt.pause(0.001)


print("sim complete")

pose_est = np.array([x[:3] for x in eta_hat[:N]])
lmk_est = [eta_hat_k[3:].reshape(-1, 2) for eta_hat_k in eta_hat[:N]]
lmk_est_final = lmk_est[N - 1]

np.set_printoptions(precision=4, linewidth=100)

# %% Plotting of results

mins = np.amin(landmarks, axis=0)
maxs = np.amax(landmarks, axis=0)

ranges = maxs - mins
offsets = ranges * 0.2

mins -= offsets
maxs += offsets

fig2, ax2 = plt.subplots(num=2, clear=True)
# landmarks
ax2.scatter(*landmarks.T, c="r", marker="^")
ax2.scatter(*lmk_est_final.T, c="b", marker=".")
# Draw covariance ellipsis of measurements
for l, lmk_l in enumerate(lmk_est_final):
    idxs = slice(3 + 2 * l, 3 + 2 * l + 2)
    rI = P_hat[N - 1][idxs, idxs]
    el = ellipse(lmk_l, rI, 5, 200)
    ax2.plot(*el.T, "b")

ax2.plot(*poseGT.T[:2], c="r", label="gt")
ax2.plot(*pose_est.T[:2], c="g", label="est")
ax2.plot(*ellipse(pose_est[-1, :2], P_hat[N - 1][:2, :2], 5, 200).T, c="g")
ax2.set(title="Estimation results", xlim=(mins[0], maxs[0]), ylim=(mins[1], maxs[1]))
ax2.axis("equal")
ax2.grid()

# %% Consistency

# NIS

fig3, ax3 = plt.subplots(nrows=3, ncols=1, figsize=(7, 5), num=3, clear=True, sharex=True)
tags = ['all', 'range', 'bearing']
dfs = [2, 1, 1]
NISes = [NISnorm, NISrange_norm, NISbearing_norm]
CIs = [CInorm, CI_1dim_norm, CI_1dim_norm]
for ax, tag, NIS, CI_NIS, df in zip(ax3, tags, NISes, CIs, dfs):
    ax.plot(np.full(N, CI_NIS[:N,0]), '--')
    ax.plot(np.full(N, CI_NIS[:N,1]), '--')
    ax.plot(NIS[:N], lw=0.5)
    insideCI = (CI_NIS[:N,0] <= NIS[:N]) * (NIS[:N] <= CI_NIS[:N,1])
    ax.set_title(f'NIS {tag}: {(insideCI.mean()*100):.2f}% inside CI, ANIS = {(NIS.mean()):.2f} with mean CI = [{(CI_NIS[:,0].mean()):.2f}, {(CI_NIS[:,1].mean()):.2f}]')

fig3.tight_layout()


# NEES
fig4, ax4 = plt.subplots(nrows=3, ncols=1, figsize=(7, 5), num=4, clear=True, sharex=True)
tags = ['all', 'position', 'heading']
dfs = [3, 2, 1]

for ax, tag, NEES, df in zip(ax4, tags, NEESes.T, dfs):
    CI_NEES = chi2.interval(1-alpha, df)
    ax.plot(np.full(N-1, CI_NEES[0]), '--')
    ax.plot(np.full(N-1, CI_NEES[1]), '--')
    ax.plot(NEES[:N-1], lw=0.5)
    insideCI = (CI_NEES[0] <= NEES) * (NEES <= CI_NEES[1])
    ax.set_title(f'NEES {tag}: {(insideCI.mean()*100):.2f}% inside CI, ANEES = {(NEES.mean()):.2f} with CI = [{(CI_NEES[0]):.2f}, {(CI_NEES[1]):.2f}]')

    CI_ANEES = np.array(chi2.interval(1-alpha, df*N)) / N
    print(f"CI ANEES {tag}: {CI_ANEES}")
    print(f"ANEES {tag}: {NEES.mean()}")

fig4.tight_layout()


# %% RMSE

ylabels = ['m', 'deg']
scalings = np.array([1, 180/np.pi])

fig5, ax5 = plt.subplots(nrows=2, ncols=1, figsize=(7, 5), num=5, clear=True, sharex=True)

pos_err = np.linalg.norm(pose_est[:N,:2] - poseGT[:N,:2], axis=1)
heading_err = np.abs(utils.wrapToPi(pose_est[:N,2] - poseGT[:N,2]))

errs = np.vstack((pos_err, heading_err))

for ax, err, tag, ylabel, scaling in zip(ax5, errs, tags[1:], ylabels, scalings):
    ax.plot(err*scaling)
    ax.set_title(f"{tag} error: RMSE {(np.sqrt((err**2).mean())*scaling):.3f} {ylabel}")
    ax.set_ylabel(f"[{ylabel}]")
    ax.grid()

fig5.tight_layout()

# %% Map and total eta NEES
mapEtaNEES = np.zeros(N)
mapEtaNEESavg = np.zeros(N)
for stepIdx, currentLmkEst in enumerate(lmk_est):
    closestLandmarkIndices = []
    for idx, est in enumerate(currentLmkEst):
        closestLandmarkIndices.append( (la.norm(est-landmarks, axis = 1)).argmin() ) # Index of the closest landmark to estimate
        
    mapPosErr = (currentLmkEst - landmarks[closestLandmarkIndices]).ravel()
    mapEtaNEES[stepIdx] = mapPosErr @ la.solve(P_hat[stepIdx][3:,3:], mapPosErr)
    if (len(closestLandmarkIndices) != 0):
        mapEtaNEESavg[stepIdx] = mapEtaNEES[stepIdx] / len(closestLandmarkIndices)
        
fig6, ax6 = plt.subplots(num=6, clear=True)
ax6.plot(mapEtaNEESavg)
ax6.set_title('Map estimate NEES (averaged over landmarks)')
ax6.set_xlabel('Time step')
plt.yscale('log')
        

# %% Movie time

if playMovie:
    try:
        print("recording movie...")

        from celluloid import Camera

        pauseTime = 0.05
        fig_movie, ax_movie = plt.subplots(num=6, clear=True)

        camera = Camera(fig_movie)

        ax_movie.grid()
        ax_movie.set(xlim=(mins[0], maxs[0]), ylim=(mins[1], maxs[1]))
        camera.snap()

        for k in tqdm(range(N)):
            ax_movie.scatter(*landmarks.T, c="r", marker="^")
            ax_movie.plot(*poseGT[:k, :2].T, "r-")
            ax_movie.plot(*pose_est[:k, :2].T, "g-")
            ax_movie.scatter(*lmk_est[k].T, c="b", marker=".")

            if k > 0:
                el = ellipse(pose_est[k, :2], P_hat[k][:2, :2], 5, 200)
                ax_movie.plot(*el.T, "g")

            numLmk = lmk_est[k].shape[0]
            for l, lmk_l in enumerate(lmk_est[k]):
                idxs = slice(3 + 2 * l, 3 + 2 * l + 2)
                rI = P_hat[k][idxs, idxs]
                el = ellipse(lmk_l, rI, 5, 200)
                ax_movie.plot(*el.T, "b")

            camera.snap()
        animation = camera.animate(interval=100, blit=True, repeat=False)
        print("playing movie")

    except ImportError:
        print(
            "Install celluloid module, \n\n$ pip install celluloid\n\nto get fancy animation of EKFSLAM."
        )

plt.show()
# %%
