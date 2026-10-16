function results = run_dsis_version_a(subjectId, validateOnly, previewOnly)
% RUN_DSIS_VERSION_A DSIS rating of Version A of the multi-scene gMAD selection.
%   run_dsis_version_a('S01')
%   plan = run_dsis_version_a('S01', true); % Validate without opening a window.
%   run_dsis_version_a('S01', false, true); % Windowed preview if fullscreen sync fails
% Version A: 10 gMAD pairs per scene from 13 scenes (28 shots), i.e. every
% video in those pairs. Each test video is shown after its own shot's
% 1080p120 reference. Settings, keys and resume behaviour are those of
% run_dsis_gmad_480p1080p.m; a session ends after SESSION_TRIALS ratings.
if nargin < 2, validateOnly = false; end
if nargin < 3, previewOnly = false; end
workspace = fileparts(fileparts(fileparts(mfilename('fullpath'))));
resultsRoot = fullfile(workspace, 'VQA2-gmad-pooling', 'results');
recipeFile = fullfile(resultsRoot, 'gmad_all_shots_480p720p1080p_skip_negative_no_offset_time_converted', ...
    'selection_all_scenes', 'video_recipes.json');
outDir = fullfile(resultsRoot, 'dsis_all_shots_version_a');
if nargin < 1, subjectId = []; end
results = run_dsis_gmad_480p1080p(subjectId, validateOnly, previewOnly, recipeFile, outDir);
end
