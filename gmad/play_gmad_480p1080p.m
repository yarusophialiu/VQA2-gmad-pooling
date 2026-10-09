function pairs = play_gmad_480p1080p(validateOnly, previewOnly)
% PLAY_GMAD_480P1080P Play bistro's 480p/720p/1080p x 30/60/120 fps pilot.
%   play_gmad_480p1080p
%   pairs = play_gmad_480p1080p(true); % Validate without opening a window.
%   play_gmad_480p1080p(false, true); % Windowed preview if fullscreen sync fails
% Uses the fullscreen/window settings in play_gmad_all_resolutions.m.
% Left=A; Right=B; Enter=next pair (0.5 s black, th
% en loading); Esc=quit.
if nargin < 1, validateOnly = false; end
if nargin < 2, previewOnly = false; end
workspace = fileparts(fileparts(fileparts(mfilename('fullpath'))));
pairList = fullfile(workspace, 'VQA2-gmad-pooling', 'results', ...
    'gmad_bistro_480p720p1080p_skip_negative_no_offset_time_converted', 'pilot_pairs.csv');
% Reject a mismatched list before starting a playback session.
pairs = play_gmad_all_resolutions(true, pairList);
for suffix = {'a', 'b'}
    for row = 1:height(pairs)
        labels = strtrim(split(pairs.(['settings_' suffix{1}])(row), '/'));
        for chunk = 1:numel(labels)
            assert(~isempty(regexp(char(labels(chunk)), '^(480|720|1080)p(30|60|120)$', 'once')), ...
                'gmad:WrongConditions', 'This player expects only 480p/720p/1080p at 30/60/120 fps.');
        end
    end
end
if ~validateOnly
    pairs = play_gmad_all_resolutions(false, pairList, [], previewOnly);
end
end
