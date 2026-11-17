# -*- coding: utf-8 -*-
"""
万方科研诚信培训平台（cx.wanfangdata.com.cn/e-training）自动刷课引擎

页面结构（逆向自站点前端 bundle，v-app）：
  活动页  /e-training/activity/info?aId=xxx
          .progress .course-box .course-list .course-item
              .course-name            课程名
              .course-right img       已完成图标
  课程介绍 /e-training/quality/introduction?courseId=xxx
          .studySoon-btn              「立即学习」
  学习页  /e-training/quality/courselearn?courseId=xxx
          #leftBox  .tree-menu li.tree_item > span.firstSpan
                    span.index / span.course-index 编号
                    span.tree-name                课时名（已学完带 complete-name）
          #rightBox .title_box h1                "1.1.1 课时名"
                    .progress-count              「课件完成条件」
                        .el-progress-bar__innerText   "45%"
                        文本 "时长进度: 1分30秒 / 10分00秒"
                        span.next                下一课（末节为 span.next-no-active）
                        span.last                上一课
          video                                 阿里播放器内核
"""

import os
import re
import time
import traceback
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

BASE = "https://cx.wanfangdata.com.cn/e-training/"

# 注入到每个新文档：屏蔽切后台暂停、记录 window.open、维持倍速
INIT_JS = r"""
(function(){
  try{ window.__wf = window.__wf || {rate: __RATE__, blockOpen: false, lastOpen: null}; }catch(e){}
  try{
    Object.defineProperty(document,'hidden',{configurable:true,get:function(){return false;}});
    Object.defineProperty(document,'visibilityState',{configurable:true,get:function(){return 'visible';}});
    document.addEventListener('visibilitychange',function(e){e.stopImmediatePropagation();},true);
  }catch(e){}
  try{
    var _open = window.open;
    window.open = function(u){
      try{ window.__wf.lastOpen = u; }catch(e){}
      if(window.__wf && window.__wf.blockOpen) return null;
      return _open.apply(window, arguments);
    };
  }catch(e){}
  setInterval(function(){
    try{
      var v = document.querySelector('video');
      if(!v) return;
      var r = (window.__wf && window.__wf.rate) || 1;
      if(Math.abs(v.playbackRate - r) > 0.01){ try{ v.playbackRate = r; }catch(e){} }
      if(!v.muted){ try{ v.muted = true; }catch(e){} }
    }catch(e){}
  }, 1000);
})();
"""

READ_STATE_JS = r"""
return (function(){
  var r = {url: location.href, title:'', progress:null, hasPanel:false, quiz:false,
           pdf:false, hasNext:false, nextTitle:'', durCur:null, durTotal:null,
           vt:null, vd:null, ended:false, paused:null, activeCode:'', activeDone:false};
  try{
    var h = document.querySelector('#rightBox .title_box h1');
    if(h) r.title = (h.innerText||'').replace(/\s+/g,' ').trim();
    if(document.querySelector('#rightBox .quiz') || /随堂测验/.test(r.title)) r.quiz = true;
    if(document.querySelector('#blank')) r.pdf = true;

    var box = document.querySelector('#rightBox .progress-count');
    if(box){
      r.hasPanel = true;
      var t = box.innerText || '';
      var it = box.querySelector('.el-progress-bar__innerText');
      if(it){ var m = (it.innerText||'').match(/(\d+)/); if(m) r.progress = parseInt(m[1],10); }
      if(r.progress === null){
        var m2 = t.match(/播放进度[：:]\s*(\d+)\s*%/); if(m2) r.progress = parseInt(m2[1],10);
      }
      if(r.progress === null){
        var b = box.querySelector('.el-progress-bar__inner');
        if(b){ var w = parseFloat(b.style.width||''); if(!isNaN(w)) r.progress = Math.round(w); }
      }
      var m3 = t.match(/时长进度[：:]?\s*([0-9时分秒]+)\s*\/\s*([0-9时分秒]+)/);
      if(m3){ r.durCur = m3[1]; r.durTotal = m3[2]; }
      var nx = box.querySelector('.next');
      if(nx){ r.hasNext = true; r.nextTitle = nx.getAttribute('title')||''; }
    }

    var act = document.querySelector('#leftBox .firstSpan.active');
    if(act){
      var li = act.closest('li');
      var idxEl = li ? (li.querySelector('.course-index') || li.querySelector('.index')) : null;
      if(idxEl) r.activeCode = idxEl.innerText.trim();
      var nm = li ? li.querySelector('.tree-name') : null;
      if(nm) r.activeDone = /complete/.test(nm.className);
      if(li && li.querySelector('.firstSpan img')) r.activeDone = true;
    }

    var v = document.querySelector('video');
    if(v){ r.vt = v.currentTime; r.vd = v.duration; r.ended = v.ended; r.paused = v.paused; }
  }catch(e){}
  return r;
})()
"""

LEAVES_JS = r"""
return (function(){
  var out = [];
  var lis = document.querySelectorAll('#leftBox li.tree_item');
  for(var i=0;i<lis.length;i++){
    var li = lis[i];
    var hasChild = false;
    for(var j=0;j<li.children.length;j++){
      var c = li.children[j];
      if(c.tagName === 'UL' && c.className.indexOf('childUl') >= 0){ hasChild = true; break; }
    }
    if(hasChild) continue;
    var sp = li.querySelector('.firstSpan');
    if(!sp) continue;
    var idxEl = li.querySelector('.course-index') || li.querySelector('.index');
    var nameEl = li.querySelector('.tree-name');
    var name = nameEl ? nameEl.innerText.trim() : (sp.innerText||'').replace(/\s+/g,' ').trim();
    var code = idxEl ? idxEl.innerText.trim() : '';
    var done = false;
    if(nameEl && /complete/.test(nameEl.className)) done = true;
    var imgs = sp.querySelectorAll('img');
    for(var k=0;k<imgs.length;k++){
      var rr = imgs[k].style && imgs[k].style.right;
      if(rr && rr.indexOf('-') === 0) done = true;
    }
    out.push({code: code, name: name, done: done,
              active: sp.className.indexOf('active') >= 0,
              quiz: /随堂测验/.test(name)});
  }
  return out;
})()
"""

CLICK_LEAF_JS = r"""
var code = arguments[0];
var lis = document.querySelectorAll('#leftBox li.tree_item');
for(var i=0;i<lis.length;i++){
  var li = lis[i];
  var hasChild = false;
  for(var j=0;j<li.children.length;j++){
    var c = li.children[j];
    if(c.tagName === 'UL' && c.className.indexOf('childUl') >= 0){ hasChild = true; break; }
  }
  if(hasChild) continue;
  var idxEl = li.querySelector('.course-index') || li.querySelector('.index');
  if(!idxEl) continue;
  if(idxEl.innerText.trim() !== code) continue;
  var sp = li.querySelector('.firstSpan');
  if(!sp) return false;
  sp.click();
  return true;
}
return false;
"""

ENSURE_PLAY_JS = r"""
return (function(){
  var v = document.querySelector('video');
  if(!v) return 'novideo';
  if(v.ended) return 'ended';
  try{ v.muted = true; }catch(e){}
  try{ var r=(window.__wf&&window.__wf.rate)||1; if(Math.abs(v.playbackRate-r)>0.01) v.playbackRate=r; }catch(e){}
  if(v.paused){ try{ var p=v.play(); if(p&&p.catch) p.catch(function(){}); }catch(e){} return 'resume'; }
  return 'playing';
})()
"""

CLICK_NEXT_JS = r"""
return (function(){
  var nx = document.querySelector('#rightBox .progress-count .next');
  if(nx){ nx.click(); return true; }
  return false;
})()
"""

HAS_NEXT_JS = r"""
return (function(){ return !!document.querySelector('#rightBox .progress-count .next'); })()
"""

COURSES_VUE_JS = r"""
return (function(){
  function pick(list){
    return list.map(function(c){
      return {courseId: c.courseId, name: c.courseName || c.name, cls: c.courseClass,
              qualified: !!c.isqualified, learned: c.learnedCount, total: c.courseCount};
    });
  }
  function find(vm, d){
    if(!vm || d > 60) return null;
    try{
      var a = vm.activity;
      if(a && a.activityCourseLearns && a.activityCourseLearns.length) return a.activityCourseLearns;
    }catch(e){}
    var ch = vm.$children || [];
    for(var i=0;i<ch.length;i++){ var r = find(ch[i], d+1); if(r) return r; }
    return null;
  }
  function scanState(o, d, seen){
    if(!o || d > 4 || typeof o !== 'object') return null;
    try{ if(seen.indexOf(o) >= 0) return null; seen.push(o); }catch(e){}
    try{
      if(Array.isArray(o)){
        if(o.length && o[0] && o[0].courseId && (o[0].courseName || o[0].name)) return o;
        for(var i=0;i<o.length && i<20;i++){ var r = scanState(o[i], d+1, seen); if(r) return r; }
        return null;
      }
      if(o.activityCourseLearns && o.activityCourseLearns.length) return o.activityCourseLearns;
      for(var k in o){
        if(k.charAt(0) === '$') continue;
        var v = o[k];
        if(v && typeof v === 'object'){
          var r2 = scanState(v, d+1, seen);
          if(r2) return r2;
        }
      }
    }catch(e){}
    return null;
  }
  var root = document.querySelector('#app');
  if(!root || !root.__vue__) return null;
  var list = find(root.__vue__, 0);
  if(!list){
    try{ list = scanState(root.__vue__.$store && root.__vue__.$store.state, 0, []); }catch(e){}
  }
  if(!list || !list.length) return null;
  return pick(list);
})()
"""

DIAG_JS = r"""
return (function(){
  function n(sel){ try{ return document.querySelectorAll(sel).length; }catch(e){ return -1; } }
  return {
    url: location.href,
    title: document.title,
    counts: {
      courseItem: n('.course-item'),
      courseList: n('.course-list'),
      progress: n('.progress'),
      leftBox: n('#leftBox'),
      learnBox: n('#courseLearnBox'),
      treeItem: n('#leftBox li.tree_item'),
      progressPanel: n('#rightBox .progress-count'),
      password: n('input[type=password]'),
      iframe: n('iframe'),
      video: n('video')
    },
    text: (document.body ? document.body.innerText : '').replace(/\n{3,}/g, '\n\n').slice(0, 4000)
  };
})()
"""

LOGIN_JS = r"""
return (function(){
  var pwd = document.querySelector('input[type=password]');
  var href = location.href;
  var onActivity = href.indexOf('activity/info') >= 0 || href.indexOf('activity/infoOld') >= 0;
  var onLearn = document.querySelectorAll('#courseLearnBox, #leftBox').length > 0;
  var cards = document.querySelectorAll('.course-item').length;
  var ready = (onActivity && cards > 0) || onLearn;
  var onAuth = href.indexOf('/auth/') >= 0 || href.indexOf('/realms/') >= 0;
  return {needLogin: !!pwd || onAuth, ready: ready, href: href,
          onAuth: onAuth, hasForm: !!pwd, courseItem: cards, onActivity: onActivity};
})()
"""

# Keycloak 登录页：#username / #password / #kc-login
FILL_LOGIN_JS = r"""
var user = arguments[0], pass = arguments[1];
function setVal(el, val){
  var d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
  d.set.call(el, val);
  el.dispatchEvent(new Event('input', {bubbles:true}));
  el.dispatchEvent(new Event('change', {bubbles:true}));
  el.dispatchEvent(new Event('blur', {bubbles:true}));
}
var pw = document.querySelector('#password') || document.querySelector('input[type=password]');
if(!pw) return false;
var un = document.querySelector('#username')
      || document.querySelector('input[name=username]')
      || [].slice.call(document.querySelectorAll('input')).filter(function(i){
           return i !== pw && (i.type === 'text' || i.type === 'tel' || !i.type);
         })[0];
if(!un) return false;
setVal(un, user);
setVal(pw, pass);
var btn = document.querySelector('#kc-login')
       || document.querySelector('input[type=submit]')
       || document.querySelector('button[type=submit]');
if(btn){ btn.click(); return true; }
var f = pw.closest('form');
if(f){ f.submit(); return true; }
return false;
"""


def hms_to_sec(s):
    if not s:
        return None
    m = re.match(r"(?:(\d+)时)?(?:(\d+)分)?(?:(\d+)秒)?$", s.strip())
    if not m or not any(m.groups()):
        return None
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Runner(object):
    def __init__(self, cfg, log, state, stop_event):
        self.cfg = cfg
        self.log = log
        self.state = state
        self.stop = stop_event
        self.driver = None
        self.records = []

    # ---------------- 基础 ----------------
    def _sleep(self, sec):
        end = time.time() + sec
        while time.time() < end:
            if self.stop.is_set():
                return False
            time.sleep(0.2)
        return True

    def _js(self, script, *args):
        return self.driver.execute_script(script, *args)

    def _read(self):
        try:
            return self._js(READ_STATE_JS)
        except Exception:
            return None

    # ---------------- 浏览器 ----------------
    def _make_driver(self):
        browser = (self.cfg.get("browser") or "edge").lower()
        path = (self.cfg.get("driver_path") or "").strip()
        if browser == "chrome":
            opt = ChromeOptions()
            svc = ChromeService(executable_path=path) if path else ChromeService()
        else:
            opt = EdgeOptions()
            svc = EdgeService(executable_path=path) if path else EdgeService()

        opt.add_argument("--start-maximized")
        opt.add_argument("--window-size=1500,950")
        opt.add_argument("--autoplay-policy=no-user-gesture-required")
        opt.add_argument("--disable-blink-features=AutomationControlled")
        opt.add_argument("--no-first-run")
        opt.add_argument("--no-default-browser-check")
        opt.add_argument("--disable-infobars")
        if self.cfg.get("mute", True):
            opt.add_argument("--mute-audio")
        opt.add_experimental_option("excludeSwitches", ["enable-automation"])
        opt.add_experimental_option("useAutomationExtension", False)
        opt.add_experimental_option("prefs", {"credentials_enable_service": False,
                                              "profile.password_manager_enabled": False})

        self.log("启动浏览器：%s" % ("Chrome" if browser == "chrome" else "Edge"))
        drv = webdriver.Chrome(options=opt, service=svc) if browser == "chrome" else webdriver.Edge(options=opt, service=svc)
        drv.set_page_load_timeout(90)
        return drv

    def _inject(self):
        rate = float(self.cfg.get("rate") or 1)
        js = INIT_JS.replace("__RATE__", str(rate))
        try:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": js})
        except Exception as e:
            self.log("注入脚本失败（不影响主流程）：%s" % e)

    def _open(self, url):
        self.driver.get(url)
        self._sleep(1.5)

    # ---------------- 登录 ----------------
    def _ensure_login(self):
        try:
            timeout = int(self.cfg.get("login_timeout", 600))
        except Exception:
            timeout = 600
        timeout = max(180, timeout)          # 至少给 3 分钟
        deadline = time.time() + timeout
        filled = False
        warned = False
        backs = 0
        last_url = ""
        last_tip = 0.0
        while time.time() < deadline:
            if self.stop.is_set():
                return False
            try:
                st = self._js(LOGIN_JS) or {}
            except Exception:
                st = {}
            href = st.get("href") or ""
            if href and href != last_url:
                last_url = href
                self.log("当前页面：%s" % href[:120])

            if st.get("ready"):
                self.log("已进入课程页面（课程卡片 %d 个）" % int(st.get("courseItem") or 0))
                return True

            if st.get("needLogin"):
                phone = (self.cfg.get("phone") or "").strip()
                pwd = (self.cfg.get("password") or "").strip()
                if phone and pwd and not filled and st.get("hasForm"):
                    filled = True
                    try:
                        ok = self._js(FILL_LOGIN_JS, phone, pwd)
                        self.log("已自动填写账号密码" + ("并提交" if ok else "（未找到登录按钮，请手动点击）"))
                    except Exception as e:
                        self.log("自动登录失败：%s" % e)
                    self._sleep(3)
                    continue
                if not warned:
                    warned = True
                    self.log(">>> 需要登录：请在浏览器窗口内完成登录，程序会自动继续（最多等待 %d 分钟）"
                             % max(1, timeout // 60))
            else:
                # 登录后常被重定向到首页，回到活动页并等待渲染
                if backs < 8:
                    backs += 1
                    self.log("回到活动页面（第 %d 次）…" % backs)
                    try:
                        self._open(self.cfg["url"])
                    except Exception:
                        pass
                    for _ in range(15):
                        if self.stop.is_set():
                            return False
                        try:
                            if (self._js(LOGIN_JS) or {}).get("ready"):
                                self.log("已进入课程页面")
                                return True
                        except Exception:
                            pass
                        self._sleep(1)
                    continue
                elif time.time() - last_tip > 20:
                    last_tip = time.time()
                    self.log("仍未发现课程列表，当前地址：%s" % href[:120])
            self._sleep(2)
        self.log("等待登录超时")
        self._dump_debug("login_timeout")
        return False

    def _dump_debug(self, tag):
        try:
            info = self._js(DIAG_JS) or {}
            html = self.driver.page_source or ""
            d = self.cfg.get("app_dir") or os.getcwd()
            os.makedirs(d, exist_ok=True)
            fp = os.path.join(d, "debug_%s_%s.txt" % (tag, datetime.now().strftime("%m%d_%H%M%S")))
            with open(fp, "w", encoding="utf-8") as f:
                f.write("URL: %s\nTITLE: %s\nCOUNTS: %s\n\n==== TEXT ====\n%s\n\n==== HTML ====\n%s"
                        % (info.get("url"), info.get("title"), info.get("counts"),
                           info.get("text"), html[:120000]))
            self.log("已保存页面诊断文件：%s" % fp)
            return fp
        except Exception as e:
            self.log("保存诊断失败：%s" % e)
            return None

    # ---------------- 课程列表 ----------------
    def _scan_courses(self):
        try:
            data = self._js(COURSES_VUE_JS)
        except Exception:
            data = None
        if data:
            self.log("读取到 %d 门课程" % len(data))
            return data

        self.log("未能直接读取课程数据，改用页面元素解析")
        try:
            self._js("window.__wf && (window.__wf.blockOpen = true)")
        except Exception:
            pass
        out = []
        # 多个候选选择器：站点结构可能随版本变化
        sel = ""
        for s in (".progress .course-list .course-item", ".course-list .course-item",
                  ".course-item", "[class*=course-item]"):
            try:
                cnt = int(self._js("return document.querySelectorAll(arguments[0]).length", s) or 0)
            except Exception:
                cnt = 0
            if cnt:
                sel = s
                self.log("课程卡片选择器：%s（%d 个）" % (s, cnt))
                break
        if not sel:
            self.log("页面上找不到课程卡片，已保存诊断文件供排查")
            self._dump_debug("no_course")
            return []

        try:
            n = int(self._js("return document.querySelectorAll(arguments[0]).length", sel) or 0)
        except Exception:
            n = 0
        for i in range(n):
            name = ""
            qualified = False
            cid = ""
            try:
                info = self._js(
                    "var it=document.querySelectorAll(arguments[0])[arguments[1]];"
                    "if(!it) return null;"
                    "var nm=it.querySelector('.course-name')||it;"
                    "var im=it.querySelector('.course-right img');"
                    "return {name: nm.innerText.trim(), src: im?im.src:''};", sel, i) or {}
                name = (info.get("name") or "").strip().split("\n")[0]
                qualified = "course-complete" in (info.get("src") or "")
            except Exception:
                pass
            try:
                self._js("window.__wf.lastOpen = null")
                self._js(
                    "var it=document.querySelectorAll(arguments[0])[arguments[1]];"
                    "if(!it) return false;"
                    "var nm=it.querySelector('.course-name')||it;"
                    "nm.click(); return true;", sel, i)
                self._sleep(0.6)
                url = self._js("return window.__wf ? window.__wf.lastOpen : null") or ""
                m = re.search(r"courseId=([0-9a-zA-Z-]+)", url)
                if m:
                    cid = m.group(1)
            except Exception:
                pass
            if name or cid:
                out.append({"courseId": cid, "name": name, "cls": "", "qualified": qualified,
                            "learned": None, "total": None})
        try:
            self._js("window.__wf && (window.__wf.blockOpen = false)")
        except Exception:
            pass
        res = [c for c in out if c.get("courseId")]
        if not res:
            self.log("课程卡片存在但无法取得 courseId，已保存诊断文件")
            self._dump_debug("no_course_id")
        return res

    def _scan_from_list(self):
        """兜底：从「我的学习」列表页按 courseId 抓取全部课程"""
        js = r"""
        return (function(){
          var out = [], seen = {};
          var as = document.querySelectorAll('a[href*="courseId="]');
          for(var i=0;i<as.length;i++){
            var m = /courseId=([0-9a-zA-Z-]+)/.exec(as[i].href);
            if(!m || seen[m[1]]) continue;
            seen[m[1]] = 1;
            var box = as[i].closest('.course') || as[i].closest('.course-item') || as[i].parentElement;
            var t = box ? box.querySelector('.title span, .title, .course-name') : null;
            out.push({courseId: m[1], name: t ? t.innerText.trim() : '', href: as[i].href});
          }
          return out;
        })()
        """
        for path in ("lecture/list", "quality/list", "personal/study"):
            if self.stop.is_set():
                return []
            try:
                self._open(BASE + path)
            except Exception:
                continue
            self._sleep(4)
            try:
                data = self._js(js) or []
            except Exception:
                data = []
            if data:
                self.log("从「%s」页读取到 %d 门课程" % (path, len(data)))
                return [{"courseId": c["courseId"], "name": c.get("name") or c["courseId"],
                         "cls": "Lecture" if "courselive" in (c.get("href") or "") else "",
                         "qualified": False, "learned": None, "total": None} for c in data]
        return []

    # ---------------- 进入课程 ----------------
    def _enter_course(self, course):
        cid = course["courseId"]
        cls = course.get("cls") or ""
        if cls == "Lecture":
            self.log("直播课程不支持自动播放，跳过：%s" % (course.get("name") or cid))
            return False
        intro = BASE + ("lecture/introduction?courseId=" if cls == "TeacherCourse" else "quality/introduction?courseId=") + cid
        self._open(intro)
        for _ in range(30):
            if self.stop.is_set():
                return False
            try:
                btn = self.driver.find_elements("css selector", ".studySoon-btn")
            except Exception:
                btn = []
            if btn:
                try:
                    self._js("arguments[0].click();", btn[0])
                except Exception:
                    try:
                        btn[0].click()
                    except Exception:
                        pass
                self._sleep(3)
                break
            self._sleep(1)

        for _ in range(30):
            if self.stop.is_set():
                return False
            try:
                if self._js("return !!document.querySelector('#courseLearnBox')"):
                    return True
            except Exception:
                pass
            self._sleep(1)

        # 兜底：直接进学习页
        for route in ("quality/courselearn?courseId=", "lecture/courselearn?courseId="):
            self._open(BASE + route + cid)
            for _ in range(20):
                try:
                    if self._js("return !!document.querySelector('#courseLearnBox')"):
                        return True
                except Exception:
                    pass
                self._sleep(1)
        return False

    # ---------------- 课时 ----------------
    def _leaves(self):
        try:
            return self._js(LEAVES_JS) or []
        except Exception:
            return []

    def _click_leaf(self, code):
        try:
            return bool(self._js(CLICK_LEAF_JS, code))
        except Exception:
            return False

    def _wait_ready(self, timeout=25):
        """等到右侧出现进度面板或测验/PDF 页面"""
        end = time.time() + timeout
        while time.time() < end:
            if self.stop.is_set():
                return None
            st = self._read()
            if st and (st.get("hasPanel") or st.get("quiz") or st.get("pdf")):
                return st
            self._sleep(1)
        return None

    def _click_next(self):
        try:
            return bool(self._js(CLICK_NEXT_JS))
        except Exception:
            return False

    def _has_next(self):
        try:
            return bool(self._js(HAS_NEXT_JS))
        except Exception:
            return False

    # ---------------- 核心：看一个课时 ----------------
    def _watch(self, course_name):
        st = self._read() or {}
        title = st.get("title") or ""
        need_dur = bool(self.cfg.get("need_duration"))
        th = int(self.cfg.get("duration_threshold", 90))

        limit = 4 * 3600
        if st.get("vd"):
            limit = int(st["vd"] * 3 + 900)
        start = time.time()
        last_tick = 0.0
        last_prog = -1
        seen_play = False

        while not self.stop.is_set():
            if time.time() - start > limit:
                self.log("⚠ 本课时超时，跳过：%s" % title)
                return "timeout"

            st = self._read()
            if not st:
                self._sleep(2)
                continue
            if not st.get("hasPanel"):
                # 页面已经切换（例如自动跳转）
                return "changed"

            prog = st.get("progress")
            cur = hms_to_sec(st.get("durCur"))
            total = hms_to_sec(st.get("durTotal"))
            ratio = (cur * 100.0 / total) if (cur is not None and total) else None

            if prog is not None and prog >= 100:
                # 阈值给 1% 容差，避免四舍五入卡在 99%
                if need_dur and ratio is not None and ratio < max(0, th - 1):
                    # 1 倍速下不应出现；出现则继续播放等时长
                    self._js(ENSURE_PLAY_JS)
                    if time.time() - last_tick > 10:
                        last_tick = time.time()
                        self.log("   播放进度 100%%，等待时长进度（%d%%/%d%%）" % (int(ratio), th))
                    self._sleep(self.cfg.get("poll", 3))
                    continue
                self.log("✔ 完成：%s（播放进度 100%%%s）"
                         % (title, "，时长进度 %d%%" % int(ratio) if ratio is not None else ""))
                return "done"

            r = self._js(ENSURE_PLAY_JS)
            if r == "novideo":
                self._sleep(2)
                continue
            if r == "ended" and (prog is None or prog < 100):
                # 播完了但进度没到 100：稍等心跳同步
                if time.time() - last_tick > 8:
                    last_tick = time.time()
                    self.log("   视频已结束，等待进度同步…（当前 %s%%）" % prog)
                self._sleep(2)
                continue

            if r in ("playing", "resume"):
                seen_play = True

            if time.time() - last_tick > 20 or (prog is not None and last_prog >= 0 and abs(prog - last_prog) >= 10):
                last_tick = time.time()
                last_prog = prog if prog is not None else last_prog
                extra = ""
                if ratio is not None:
                    extra = " | 时长进度 %d%%" % int(ratio)
                self.log("   %s%%%s" % (prog if prog is not None else "?", extra))

            self._sleep(self.cfg.get("poll", 3))

        return "stop"

    # ---------------- 刷一门课 ----------------
    def _learn_course(self, course):
        name = course.get("name") or course.get("courseId")
        self.state("正在学习：%s" % name)
        self.log("")
        self.log("===== 课程：%s =====" % name)

        if not self._enter_course(course):
            self.log("✘ 进入学习页失败：%s" % name)
            return False

        leaves = self._leaves()
        if not leaves:
            self.log("✘ 未识别到课程目录")
            return False
        total = len([x for x in leaves if not x.get("quiz")])
        done = len([x for x in leaves if x.get("done") and not x.get("quiz")])
        self.log("目录：共 %d 个视频课时，已完成 %d 个" % (total, done))

        idx = self._next_index(leaves, None)
        if idx is None:
            self.log("本课程所有课时均已完成")
            return True

        guard = 0
        while not self.stop.is_set() and idx < len(leaves):
            guard += 1
            if guard > total * 4 + 30:
                self.log("⚠ 循环次数异常，结束本课程")
                break

            leaf = leaves[idx]
            code = leaf.get("code") or ""
            self.log("")
            self.log("→ 切换课时 %s %s" % (code, leaf.get("name") or ""))
            if not self._click_leaf(code):
                self.log("   目录中未找到该课时，跳过")
                idx += 1
                continue

            st = self._wait_ready(30)
            if st is None:
                self.log("✘ 学习页加载超时")
                break

            title = st.get("title") or leaf.get("name") or ""

            # 测验 / PDF / 已学完：跳过
            if st.get("quiz") or st.get("pdf"):
                self.log("   跳过%s：%s" % ("随堂测验" if st.get("quiz") else "PDF 课件", title))
                leaves = self._leaves()
                idx = self._next_index(leaves, code)
                if idx is None:
                    break
                continue

            if st.get("activeDone"):
                self.log("   已学完，跳过：%s" % title)
                leaves = self._leaves()
                idx = self._next_index(leaves, code)
                if idx is None:
                    break
                continue

            self.log("▶ 播放：%s" % title)
            self.state("正在播放：%s" % title)
            res = self._watch(name)

            if res == "stop":
                return False
            if res == "changed":
                leaves = self._leaves()
                idx = self._pick_index(leaves, self._active_code(), code)
                if idx is None:
                    break
                continue
            if res == "done":
                self._write_record(name, title)

            # 优先点「下一课」：会先调用 insertrecord 保存进度
            if self._has_next() and self._click_next():
                self._sleep(2)
                cur = self._active_code()
                leaves = self._leaves()
                idx = self._pick_index(leaves, cur, code)
                if idx is None:
                    break
            else:
                leaves = self._leaves()
                idx = self._next_index(leaves, code)
                if idx is None:
                    self.log("■ 本课程最后一节已结束")
                    break

        self.log("===== 课程结束：%s =====" % name)
        return True

    def _active_code(self):
        try:
            st = self._read() or {}
            return st.get("activeCode") or ""
        except Exception:
            return ""

    @staticmethod
    def _next_index(leaves, after_code):
        """返回 after_code 之后第一个「未完成且非测验」的课时下标"""
        start = 0
        if after_code:
            for i, x in enumerate(leaves):
                if x.get("code") == after_code:
                    start = i + 1
                    break
        for i in range(start, len(leaves)):
            x = leaves[i]
            if x.get("quiz") or x.get("done"):
                continue
            return i
        return None

    def _pick_index(self, leaves, code, fallback=None):
        """当前已停在 code 上：若它仍需学习就用它，否则往后找"""
        if code:
            for i, x in enumerate(leaves):
                if x.get("code") == code:
                    if not x.get("quiz") and not x.get("done"):
                        return i
                    return self._next_index(leaves, code)
        return self._next_index(leaves, fallback)

    def _write_record(self, course_name, lesson_title):
        try:
            safe = re.sub(r'[\\/:*?"<>|]', "_", course_name)
            d = self.cfg.get("record_dir") or "record"
            os.makedirs(d, exist_ok=True)
            fp = os.path.join(d, "《%s》的刷课记录.txt" % safe)
            with open(fp, "a", encoding="utf-8") as f:
                f.write("已刷完:《%s》\n完成时间：%s\n\n" % (lesson_title, now_str()))
        except Exception as e:
            self.log("写记录失败：%s" % e)

    # ---------------- 主流程 ----------------
    def run(self):
        try:
            self.driver = self._make_driver()
            self._inject()
            self.log("打开活动页面…")
            self._open(self.cfg["url"])

            if not self._ensure_login():
                self.state("未登录/已停止")
                return

            if self.cfg.get("diagnose_only"):
                self.log("===== 页面诊断 =====")
                try:
                    info = self._js(DIAG_JS) or {}
                    self.log("URL：%s" % info.get("url"))
                    self.log("元素统计：%s" % info.get("counts"))
                    self.log("页面文字（前 600 字）：\n%s" % (info.get("text") or "")[:600])
                except Exception as e:
                    self.log("诊断读取失败：%s" % e)
                self._dump_debug("manual")
                self.state("诊断完成")
                return

            courses = self._scan_courses()
            if not courses:
                self.log("活动页未解析到课程，尝试从「我的学习」列表页读取…")
                courses = self._scan_from_list()

            # 兜底：已经停在某门课的学习页，直接开始学这一门
            if not courses:
                try:
                    on_learn = self._js("return !!document.querySelector('#courseLearnBox')")
                except Exception:
                    on_learn = False
                if not on_learn:
                    try:
                        self._open(self.cfg["url"])
                        self._sleep(3)
                        on_learn = self._js("return !!document.querySelector('#courseLearnBox')")
                    except Exception:
                        on_learn = False
                if on_learn:
                    m = re.search(r"courseId=([0-9a-zA-Z-]+)", self.driver.current_url)
                    title = ""
                    try:
                        title = (self._js("var h=document.querySelector('#rightBox .title_box h1');return h?h.innerText.trim():''") or "")
                    except Exception:
                        pass
                    if m:
                        self.log("检测到已在课程学习页，直接开始：%s" % title)
                        courses = [{"courseId": m.group(1), "name": title or m.group(1),
                                    "cls": "", "qualified": False, "learned": None, "total": None}]
            if not courses:
                self.log("✘ 未发现课程，请确认活动页面是否正常（已生成诊断文件）")
                return

            todo = [c for c in courses if not c.get("qualified")]
            self.log("共 %d 门课程，待学 %d 门" % (len(courses), len(todo)))

            for i, c in enumerate(todo, 1):
                if self.stop.is_set():
                    break
                self.log("")
                self.log("【%d/%d】%s" % (i, len(todo), c.get("name")))
                try:
                    self._learn_course(c)
                except Exception:
                    self.log("课程异常：%s" % c.get("name"))
                    self.log(traceback.format_exc(limit=3))
                    # 回活动页继续下一门
                    try:
                        self._open(self.cfg["url"])
                    except Exception:
                        pass

            if self.stop.is_set():
                self.log("已停止")
                self.state("已停止")
            else:
                self.log("")
                self.log("★★★ 全部课程处理完毕 ★★★")
                self.state("全部完成")
        except Exception:
            self.log("运行异常：")
            self.log(traceback.format_exc())
            self.state("异常")
        finally:
            if self.driver and self.cfg.get("close_browser"):
                try:
                    self.driver.quit()
                except Exception:
                    pass
