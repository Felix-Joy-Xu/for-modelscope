// content.js
console.log("交大 Canvas 视频插件加载 (v1.7 - 深度探查版)", window.location.href);

let hasEnded = false;
let hasStarted = false;

function showToast(msg, isError = false) {
    let toast = document.getElementById('sjtu-canvas-plugin-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'sjtu-canvas-plugin-toast';
        toast.style.cssText = "position:fixed; bottom:20px; right:20px; background:rgba(0,0,0,0.9); color:white; padding:12px 20px; border-radius:8px; z-index:9999999; font-size:15px; pointer-events:none; transition: all 0.3s; box-shadow: 0 4px 12px rgba(0,0,0,0.3);";
        document.body.appendChild(toast);
    }
    toast.style.backgroundColor = isError ? "rgba(220,53,69,0.9)" : "rgba(33,37,41,0.9)";
    toast.innerHTML = msg;
    setTimeout(() => { toast.style.opacity = '0.5'; }, 4000);
}

// 终极暴力点击
function bruteForceClick(element) {
    let current = element;
    let depth = 0;
    
    // 如果按钮在表单里，直接提交表单
    let form = current.closest('form');
    if (form) {
        console.log("检测到表单，尝试直接提交");
        try { form.submit(); } catch(e) {}
    }

    while (current && depth < 3 && current !== document.body) {
        try { current.click(); } catch(e) {}
        
        const events = ['pointerover', 'mouseover', 'mousedown', 'pointerdown', 'mouseup', 'pointerup', 'click'];
        events.forEach(eventType => {
            const event = new MouseEvent(eventType, {
                view: window,
                bubbles: true,
                cancelable: true,
                buttons: (eventType.includes('down') || eventType.includes('click')) ? 1 : 0
            });
            current.dispatchEvent(event);
        });

        const reactKey = Object.keys(current).find(key => key.startsWith('__reactEventHandlers') || key.startsWith('__reactProps'));
        if (reactKey && current[reactKey]) {
            const reactProps = current[reactKey];
            if (typeof reactProps.onClick === 'function') {
                try {
                    reactProps.onClick({ 
                        preventDefault: () => {}, 
                        stopPropagation: () => {},
                        target: current,
                        currentTarget: current
                    });
                } catch(e) {}
            }
        }
        current = current.parentElement;
        depth++;
    }
}

if (window.top === window.self && !window.location.hostname.includes('sjtu.edu.cn')) {
    // 忽略
} else {
    showToast("🔍 插件正在寻找视频...");
    setInterval(tryPlayVideo, 1000);
}

function tryPlayVideo() {
    if (hasEnded) return;

    const videos = document.querySelectorAll('video');
    if (videos.length > 0 && !hasStarted) {
        hasStarted = true;
        showToast("✅ 找到视频，尝试播放...");
    }

    videos.forEach(video => {
        if (video.paused && video.currentTime < video.duration) {
            let playPromise = video.play();
            if (playPromise !== undefined) {
                playPromise.then(() => {
                    showToast("▶️ 视频正在播放中");
                }).catch(e => {
                    showToast("⚠️ 浏览器拦截自动播放！请点一下页面空白处", true);
                });
            }
        }
        
        if (!video.dataset.autoplayBound) {
            video.dataset.autoplayBound = "true";
            video.addEventListener('ended', handleVideoEnd);
        }

        if (video.currentTime > 0 && video.duration > 0 && (video.duration - video.currentTime) < 1) {
            handleVideoEnd();
        }
    });

    const allElements = document.querySelectorAll('span, div, button, a');
    for (let el of allElements) {
        const text = el.textContent || '';
        if (text.replace(/\s/g, '').includes('再看一遍') && el.offsetParent !== null && text.length < 10) {
            handleVideoEnd();
            break;
        }
    }
}

function handleVideoEnd() {
    if (hasEnded) return;
    hasEnded = true;
    showToast("🎉 视频已结束！准备执行跳转...", false);
    
    if (attemptClickNext()) {
        return;
    }

    if (window.self !== window.top) {
        showToast("正在通知主页面跳转...");
        window.top.postMessage('canvas_video_ended', '*');
    } else {
        showToast("❌ 未找到下一页按钮！", true);
    }
}

function attemptClickNext() {
    let target = null;
    
    // Canvas 隐藏的 Next Link
    let nextLink = document.querySelector('link[rel="next"]');
    if (nextLink && nextLink.href) {
        window.location.href = nextLink.href;
        return true;
    }

    target = document.querySelector('.module-sequence-footer-button--next');

    if (!target) {
        const candidates = Array.from(document.querySelectorAll('a, button'));
        for (let el of candidates) {
            const text = (el.textContent || '').trim();
            if ((text.includes('下一页') || text.includes('下一个') || text.includes('下一节') || text.includes('Next')) && el.offsetParent !== null) {
                target = el;
                break;
            }
        }
    }
    
    if (!target) {
        const all = Array.from(document.querySelectorAll('span, div'));
        for (let el of all) {
            const text = (el.textContent || '').trim();
            if ((text.includes('下一页') || text.includes('下一个') || text.includes('下一节') || text.includes('Next')) && text.length < 20 && el.offsetParent !== null) {
                target = el.closest('a, button, div[role="button"], li') || el.parentElement || el;
                break;
            }
        }
    }

    if (target) {
        target.style.boxShadow = "0 0 0 4px red inset";
        target.style.transition = "all 0.3s";
        
        const internalLink = target.tagName === 'A' ? target : target.querySelector('a');
        
        if (internalLink && internalLink.href && !internalLink.href.endsWith('#') && !internalLink.href.startsWith('javascript:')) {
            window.location.href = internalLink.href;
        } else {
            // 依旧执行暴力点击
            bruteForceClick(target);
            
            // 如果 2 秒后页面还没跳转（通常跳转会销毁当前页面），则说明模拟点击被彻底屏蔽了
            // 此时弹出一个提取框，让我们看看这个按钮到底是个什么妖魔鬼怪
            if (!window.hasPromptedHTML) {
                window.hasPromptedHTML = true;
                setTimeout(() => {
                    // 获取它和它父元素的HTML
                    let debugHTML = target.outerHTML;
                    if (target.parentElement) {
                        debugHTML = target.parentElement.outerHTML;
                    }
                    prompt("点击已被网页底层拦截！请复制框里的代码发给AI助手，帮您查明它的真实结构：", debugHTML);
                }, 2000);
            }
        }
        return true;
    }
    
    return false;
}

window.addEventListener('message', function(event) {
    if (event.data === 'canvas_video_ended') {
        showToast("📩 收到信号，执行下一页操作...");
        if (!attemptClickNext()) {
            showToast("❌ 主页面没找到下一页按钮！", true);
        }
    }
});
