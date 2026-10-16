function pairs = play_gmad_720p1080p(validateOnly, previewOnly)
% PLAY_GMAD_720P1080P Play gMAD-selected bistro pairs using only 720p/1080p.
%   play_gmad_720p1080p
%   pairs = play_gmad_720p1080p(true); % Validate without opening a window.
%   play_gmad_720p1080p(false, true); % Windowed preview if fullscreen sync fails
% Keeps the gmad_pairs.csv rows of the 480p/720p/1080p run whose A and B
% chunks are all 720p or 1080p (30/60/120 fps), then plays them with the
% fullscreen/window settings in play_gmad_all_resolutions.m.
% Left=A; Right=B; Enter=next pair (0.5 s black, then loading); Esc=quit.
if nargin < 1, validateOnly = false; end
if nargin < 2, previewOnly = false; end
workspace = fileparts(fileparts(fileparts(mfilename('fullpath'))));
selectedList = fullfile(workspace, 'VQA2-gmad-pooling', 'results', ...
    'gmad_bistro_480p720p1080p_skip_negative_no_offset_time_converted', 'gmad_pairs.csv');
assert(isfile(selectedList), 'gmad:MissingPairs', 'Missing pair list: %s', selectedList);
% UTF-8 encoding strips the byte-order mark from the first column name.
selected = readtable(selectedList, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
keep = false(height(selected), 1);
for row = 1:height(selected)
    labels = strtrim([split(selected.settings_a(row), '/'); split(selected.settings_b(row), '/')]);
    keep(row) = all(~cellfun(@isempty, regexp(cellstr(labels), '^(720|1080)p(30|60|120)$', 'once')));
end
selected = selected(keep, :);
assert(height(selected) > 0, 'gmad:NoPairs', 'No 720p/1080p-only pairs in %s.', selectedList);
fprintf('Kept %d of %d gMAD-selected pairs (720p/1080p only).\n', nnz(keep), numel(keep));
% The shared player takes a file, so write the filtered list next to tempdir.
pairList = fullfile(tempdir, 'gmad_bistro_720p1080p_pairs.csv');
writetable(selected, pairList);
% Reject a mismatched list before starting a playback session.
pairs = play_gmad_all_resolutions(true, pairList);
if ~validateOnly
    pairs = play_gmad_all_resolutions(false, pairList, [], previewOnly);
end
end
