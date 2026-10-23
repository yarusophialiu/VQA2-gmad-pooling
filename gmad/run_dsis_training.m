function results = run_dsis_training(subjectId)
% RUN_DSIS_TRAINING Practice block to run before the DSIS experiment.
%   run_dsis_training('S01')
% Ten videos that are not part of the experiment, in a fixed order: five
% school videos (CVVDP levels 3-5, the most school can reach), then five
% sibenik videos (one per level, 1-5). Within each scene they go from most
% to least impaired. results/dsis_training/training_recipes.json lists them
% with their expected level, which is shown after each rating and, with
% SHOW_EXPECTED_LEVEL in run_dsis_gmad_480p1080p.m, top-left during the test
% video. Every run starts fresh in its own folder, so practice ratings never
% mix with experiment ratings.
if nargin < 1 || isempty(subjectId)
    subjectId = strtrim(input('Subject ID: ', 's'));
end
trainingDir = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'results', 'dsis_training');
recipeFile = fullfile(trainingDir, 'training_recipes.json');
outDir = fullfile(trainingDir, 'sessions', ...
    sprintf('%s_%s', subjectId, char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'))));
% Fixed order: the videos play in recipe-file order.
results = run_dsis_gmad_480p1080p(subjectId, false, false, recipeFile, outDir, [], true);
end
