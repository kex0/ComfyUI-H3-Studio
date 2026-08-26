"""ComfyUI-H3-Studio: Auto Chain, Music Video, Face Refine Video, Load Song, and Local Infinite Prompter."""

WEB_DIRECTORY = "./web/js"

# ComfyUI loads this file as a package. Pytest may collect the hyphenated
# custom-node root as a top-level ``__init__`` module; keep that path empty.
if __package__:
    from .auto_chain import H3StudioAutoChain, H3StudioAutoChainAdvanced
    from .music_video import H3StudioMusicVideo, H3StudioMusicVideoAdvanced
    from .song_loader import H3StudioLoadSong
    from .face_refine.video_refine import H3StudioFaceRefineVideo
    from .builder import H3StudioBuilder
    from .prompter_infinite import H3StudioLocalInfinitePrompter

    NODE_CLASS_MAPPINGS = {
        "H3StudioAutoChain": H3StudioAutoChain,
        "H3StudioAutoChainAdvanced": H3StudioAutoChainAdvanced,
        "H3StudioMusicVideo": H3StudioMusicVideo,
        "H3StudioMusicVideoAdvanced": H3StudioMusicVideoAdvanced,
        "H3StudioFaceRefineVideo": H3StudioFaceRefineVideo,
        "H3StudioLoadSong": H3StudioLoadSong,
        "H3StudioBuilder": H3StudioBuilder,
        "H3StudioLocalInfinitePrompter": H3StudioLocalInfinitePrompter,
    }
    NODE_DISPLAY_NAME_MAPPINGS = {
        "H3StudioAutoChain": "H3 Studio - Auto Chain",
        "H3StudioAutoChainAdvanced": "H3 Studio - Auto Chain Advanced",
        "H3StudioMusicVideo": "H3 Studio - Music Video",
        "H3StudioMusicVideoAdvanced": "H3 Studio - Music Video Advanced",
        "H3StudioFaceRefineVideo": "H3 Studio - Face Refine Video",
        "H3StudioLoadSong": "H3 Studio - Load Song",
        "H3StudioBuilder": "H3 Studio - Builder",
        "H3StudioLocalInfinitePrompter": "H3 Studio - Local Infinite Prompter",
    }
else:
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
