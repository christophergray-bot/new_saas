document.addEventListener("DOMContentLoaded", function () {
    const shell = document.getElementById("drake-video-shell");
    const video = document.getElementById("drake-landing-video");
    const button = document.getElementById("drake-video-play");

    if (!shell || !video || !button) return;

    const icon = button.querySelector(".drake-video-play-icon");
    const text = button.querySelector(".drake-video-play-text");

    function showPlayState(label, symbol) {
        shell.classList.remove("is-playing");
        text.textContent = label;
        icon.textContent = symbol;
        button.setAttribute("aria-label", label + " video");
    }

    async function playVideo() {
        try {
            await video.play();
            shell.classList.add("is-playing");
        } catch (error) {
            showPlayState("Play Drake", "▶");
        }
    }

    button.addEventListener("click", playVideo);

    video.addEventListener("click", function () {
        if (video.paused) {
            playVideo();
        } else {
            video.pause();
        }
    });

    video.addEventListener("pause", function () {
        if (!video.ended) showPlayState("Continue", "▶");
    });

    video.addEventListener("play", function () {
        shell.classList.add("is-playing");
    });

    video.addEventListener("ended", function () {
        video.currentTime = 0;
        showPlayState("Replay", "↻");
    });
});
