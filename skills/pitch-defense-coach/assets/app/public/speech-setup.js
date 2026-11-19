// The browser records an explicit choice; the active Agent performs installation.
// No commands, paths, or package names are accepted from the browser.
export function createSpeechSetup(api, anchor) {
  const dialog=document.createElement('dialog');
  dialog.setAttribute('aria-label','启用本机语音转写');
  dialog.innerHTML='<h2>启用本机语音转写？</h2><p>未找到能够正常加载的语音环境。可以选择安装/修复，也可以先用文字练习。</p><p>首次安装需要联网下载开源模型和运行依赖，下载量和磁盘占用因所选模型与环境而异。录音随后在本机转写，不上传到语音服务。</p><p>选择后由当前AI协助安装，页面本身不会下载。没有可执行命令的AI时，需要在本机终端完成。</p><div><button data-choice="small">安装准确优先版</button> <button data-choice="tiny">安装轻量快速版</button> <button data-choice="skip">暂不安装，文字练习</button></div><p role="status"></p>';
  document.body.append(dialog);
  const button=document.createElement('button');button.type='button';button.textContent='语音安装选项';button.hidden=true;anchor.after(button);
  const hint=document.createElement('p');hint.setAttribute('role','status');button.after(hint);
  let loaded=false,shown=false,busy=false;
  function describe(choice){hint.textContent=choice?.status==='requested'?'已记录安装选择。请在当前AI聊天发送“完成语音安装”；安装并验证前仍可使用文字练习。':choice?.status==='skipped'?'已选择暂不安装，可随时重新打开语音安装选项。':'';if(choice?.status==='skipped'){const mic=document.querySelector('#useMic');if(mic)mic.checked=false;}}
  button.onclick=()=>{if(!dialog.open)dialog.showModal();};
  dialog.addEventListener('cancel',()=>{shown=true;});
  dialog.onclick=async event=>{
    const choice=event.target.dataset.choice;if(!choice||busy)return;
    busy=true;for(const b of dialog.querySelectorAll('button'))b.disabled=true;
    try{const result=await api('asr/setup-choice',{choice});describe(result);loaded=true;shown=true;dialog.close();if(choice==='skip'){const mic=document.querySelector('#useMic');if(mic)mic.checked=false;}}
    catch(e){dialog.querySelector('[role="status"]').textContent=e.message;}
    finally{busy=false;for(const b of dialog.querySelectorAll('button'))b.disabled=false;}
  };
  return async status=>{
    if(status?.state==='ready'){button.hidden=true;hint.textContent='';if(dialog.open)dialog.close();return;}
    if(!status?.needsSetup)return;
    button.hidden=false;
    if(loaded)return;loaded=true;
    try{const state=await api('state');describe(state.speechSetup);if(!state.speechSetup&&!shown){shown=true;dialog.showModal();}}
    catch{loaded=false;}
  };
}
