# CytoNorm-in-a-box. Built once; invoked per job via `docker run`.
# Long pole of the 1-day build — build this FIRST, in the background.
#
#   docker build -f backend/docker/Dockerfile.r -t wakaflaka-r:cytonorm .
#   docker run --rm wakaflaka-r:cytonorm Rscript -e 'library(CytoNorm); cat("ok\n")'
#
# Base is the official Bioconductor image (R 4.4 / Bioc 3.20): flowCore + FlowSOM
# and their compiled deps are already prebuilt here, which is what saves the hour
# of source compilation that makes a from-scratch R setup blow the day.

FROM bioconductor/bioconductor_docker:RELEASE_3_20

# jsonlite = params.json parsing across the Python<->R file boundary.
# flowCore = FCS I/O; FlowSOM = CytoNorm's internal clusterer.
RUN R -e 'BiocManager::install(c("flowCore","FlowSOM"), update=FALSE, ask=FALSE)'

# CytoNorm is GitHub-only (saeyslab/CytoNorm), not on Bioconductor.
# Pin the ref for reproducibility once a known-good commit/tag is chosen.
RUN R -e 'install.packages("remotes", repos="https://cloud.r-project.org"); \
          remotes::install_github("saeyslab/CytoNorm", upgrade="never")'
RUN R -e 'install.packages("jsonlite", repos="https://cloud.r-project.org")'

# Fail the build loudly if any engine is missing, rather than at job time.
RUN R -e 'library(flowCore); library(FlowSOM); library(CytoNorm); library(jsonlite); \
          cat("R engine image OK\n")'

# The job working dir is bind-mounted at run time:
#   docker run --rm -v <abs job dir>:/job wakaflaka-r:cytonorm \
#     Rscript /job/run_cytonorm.R /job
WORKDIR /job
