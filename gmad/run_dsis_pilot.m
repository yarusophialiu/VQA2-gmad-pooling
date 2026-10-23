function results = run_dsis_pilot(subjectId, validateOnly, previewOnly)
% RUN_DSIS_PILOT DSIS pilot on a subset of Version A (under 40 min).
%   run_dsis_pilot('S01')
%   plan = run_dsis_pilot('S01', true);   % Validate without opening a window.
%   run_dsis_pilot('S01', false, true);   % Windowed preview if fullscreen sync fails
% One shot (reference) from each of several scenes, with all of its
% Version A videos, so every gMAD pair in those shots is complete; by the
% 4.5 s CVVDP score the videos span DSIS levels 1-5. gmad/build_dsis_pilot.py
% makes the selection and prints it; see results/dsis_pilot/pilot_videos.csv. Each test video is shown after its own
% shot's 1080p120 reference, in random order per subject. Settings, keys and
% resume behaviour are those of run_dsis_gmad_480p1080p.m.
if nargin < 1, subjectId = []; end
if nargin < 2, validateOnly = false; end
if nargin < 3, previewOnly = false; end
pilotDir = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'results', 'dsis_pilot');
results = run_dsis_gmad_480p1080p(subjectId, validateOnly, previewOnly, ...
    fullfile(pilotDir, 'pilot_recipes.json'), fullfile(pilotDir, 'ratings'));
end
