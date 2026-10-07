/** Accessible controls. React and peer components belong to the containing website. */
export function createDateTimeFields(React,dependencies){
 const {createElement:h,useState,useRef,useEffect,useId,useMemo}=React;
 const {DatePicker,TimeField,DateInput,DateSegment,Label,Group,Button,Popover,Dialog,
  Calendar,CalendarGrid,CalendarCell,Heading,Text,FieldError,I18nProvider,parseDate,parseTime,Time}=dependencies;
 const parsed=(value,parser)=>{try{return value?parser(value):null;}catch{return null;}};
 const icon=kind=>h('svg',{viewBox:'0 0 24 24',width:22,height:22,fill:'none',stroke:'currentColor','strokeWidth':1.7,'aria-hidden':true},
  kind==='time'?h(React.Fragment,null,h('circle',{cx:12,cy:12,r:9}),h('path',{d:'M12 6v6l4 2'})):
   h(React.Fragment,null,h('rect',{x:3,y:5,width:18,height:16,rx:2}),h('path',{d:'M7 3v4m10-4v4M3 10h18'})));
 const segments=segment=>h(DateSegment,{segment,className:'abs-date-segment'});
 // Use a fixed viewport host through the supported portal container so a positioned body does not
 // turn a viewport-relative flipped offset into an offset against the whole page.
 function usePickerPortal(){
  const [portal,setPortal]=useState(null);
  useEffect(()=>{
   const node=document.createElement('div');node.className='abs-picker-portal';
   document.body.append(node);setPortal(node);return()=>node.remove();
  },[]);
  return portal;
 }
 function useWidthDismiss(open,close){
  useEffect(()=>{
   if(!open)return;const width=window.innerWidth;
   const resize=()=>{if(window.innerWidth!==width)close(false);};
   window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);
  },[open,close]);
 }
 const hints=(description,error)=>[description?h(Text,{slot:'description',className:'abs-field-hint',key:'hint'},description):null,
  error?h(Text,{slot:'errorMessage',className:'abs-field-error',key:'error'},error):h(FieldError,{className:'abs-field-error',key:'error'})];
 function DateField({label,value='',onChange,required=false,min='',max='',disabled=false,available=true,
  description='',error='',yearJump=false,theme='',name}){
  const selected=useMemo(()=>parsed(value,parseDate),[value]),minimum=useMemo(()=>parsed(min,parseDate),[min]),maximum=useMemo(()=>parsed(max,parseDate),[max]);
  const [open,setOpen]=useState(false),[focused,setFocused]=useState(selected||maximum||minimum||parseDate('2000-01-01'));
  const [year,setYear]=useState(String(focused.year)),yearId=useId(),monthId=useId(),group=useRef(null);
  const usable=available && !disabled,portal=usePickerPortal();
  useWidthDismiss(open,setOpen);
  useEffect(()=>{if(!usable)setOpen(false);},[usable]);
  function focus(next){
   if(minimum && next.compare(minimum)<0)next=minimum;
   if(maximum && next.compare(maximum)>0)next=maximum;
   setFocused(next);setYear(String(next.year));
  }
  // React Aria closes after a Calendar selection. A segmented-input commit can
  // also fire while focus moves into the popup; that must not dismiss it.
  const change=next=>{if(!usable)return;onChange(next?.toString()||'');if(next)focus(next);};
  const fields=yearJump?h('div',{className:'abs-calendar-jump'},
   h('label',{htmlFor:monthId},'Month',h('select',{id:monthId,'aria-label':'Month',value:focused.month,onChange:event=>focus(focused.set({day:1,month:Number(event.target.value)}))},
    Array.from({length:12},(_,index)=>h('option',{key:index,value:index+1},new Intl.DateTimeFormat('en-GB',{month:'long',timeZone:'UTC'}).format(new Date(Date.UTC(2000,index,1))))))),
   h('label',{htmlFor:yearId},'Year',h('input',{id:yearId,'aria-label':'Year',type:'text',inputMode:'numeric',pattern:'[0-9]{1,4}',maxLength:4,value:year,
    onChange:event=>{const text=event.target.value;if(!/^[0-9]{0,4}$/.test(text))return;setYear(text);
     const numeric=Number(text);if(numeric>=1 && numeric<=(maximum?.year||9999))setFocused(focused.set({day:1,year:numeric}));},
    onBlur:()=>setYear(String(focused.year))}))) :null;
  return h(I18nProvider,{locale:'en-GB-u-ca-gregory'},h(DatePicker,{className:'abs-date-picker '+theme,name,
   value:selected,onChange:change,isRequired:required,minValue:minimum||undefined,maxValue:maximum||undefined,
   isDisabled:!usable,isInvalid:!!error,isOpen:open && usable,onOpenChange:setOpen,shouldForceLeadingZeros:true},
   h(Label,{className:'abs-field-label'},label),h(Group,{ref:group,className:'abs-date-group',onClickCapture:event=>{
    if(usable && event.currentTarget.contains(event.target) && !event.target.closest('button'))setOpen(true);
   }},h(DateInput,{className:'abs-date-input'},segments),h(Button,{type:'button','aria-label':'Choose '+label},icon('date'))),
   ...hints(description,error),h(Popover,{triggerRef:group,UNSTABLE_portalContainer:portal||undefined,className:'abs-booking-picker '+theme,placement:'bottom start',offset:8},h(Dialog,{'aria-label':label},
    fields,h(Calendar,{className:'abs-calendar',focusedValue:focused,onFocusChange:focus},
     h('header',null,h(Button,{slot:'previous',type:'button','aria-label':'Previous month'},'‹'),h(Heading),h(Button,{slot:'next',type:'button','aria-label':'Next month'},'›')),
     h(CalendarGrid,null,date=>h(CalendarCell,{date,className:'abs-calendar-cell'}))),
    !required?h(Button,{slot:null,type:'button',className:'abs-picker-action',onPress:()=>{change(null);setOpen(false);}},'Clear date'):null))));
 }
 function TimeFieldControl({label,value='',onChange,required=false,disabled=false,available=true,description='',error='',theme='',name}){
  const selected=useMemo(()=>parsed(value,parseTime),[value]),[open,setOpen]=useState(false),[draft,setDraft]=useState(selected||new Time(12,0));
  const group=useRef(null),hourId=useId(),minuteId=useId(),periodId=useId(),usable=available && !disabled,portal=usePickerPortal();
  useWidthDismiss(open,setOpen);
  useEffect(()=>{if(!usable)setOpen(false);},[usable]);
  const begin=()=>{if(usable){setDraft(selected||new Time(12,0));setOpen(true);}};
  const commit=next=>{if(usable){onChange(next?String(next.hour).padStart(2,'0')+':'+String(next.minute).padStart(2,'0'):'');setOpen(false);}};
  const period=draft.hour>=12?'PM':'AM',hour=draft.hour%12||12;
  return h(I18nProvider,{locale:'en-GB-u-ca-gregory'},h(React.Fragment,null,
   h(TimeField,{className:'abs-date-picker '+theme,name,value:selected,onChange:next=>{if(usable)commit(next);},isRequired:required,isDisabled:!usable,isInvalid:!!error,
    hourCycle:12,granularity:'minute',shouldForceLeadingZeros:true},h(Label,{className:'abs-field-label'},label),
    h(Group,{ref:group,className:'abs-date-group',onClickCapture:event=>{if(event.currentTarget.contains(event.target) && !event.target.closest('button'))begin();}},
     h(DateInput,{className:'abs-date-input'},segments),h(Button,{type:'button',isDisabled:!usable,'aria-label':'Choose '+label,onPress:begin},icon('time'))),...hints(description,error)),
   h(Popover,{triggerRef:group,UNSTABLE_portalContainer:portal||undefined,isOpen:open && usable,onOpenChange:setOpen,placement:'bottom start',offset:8,className:'abs-booking-picker '+theme},
    h(Dialog,{'aria-label':label},h('div',{className:'abs-time-choices'},
     h('label',{htmlFor:hourId},'Hour',h('select',{id:hourId,'aria-label':'Hour',value:hour,onChange:event=>setDraft(new Time(Number(event.target.value)%12+(period==='PM'?12:0),draft.minute))},
      Array.from({length:12},(_,index)=>h('option',{key:index,value:index+1},String(index+1).padStart(2,'0'))))),
     h('label',{htmlFor:minuteId},'Minute',h('select',{id:minuteId,'aria-label':'Minute',value:draft.minute,onChange:event=>setDraft(new Time(draft.hour,Number(event.target.value)))},
      Array.from({length:60},(_,index)=>h('option',{key:index,value:index},String(index).padStart(2,'0'))))),
     h('label',{htmlFor:periodId},'AM / PM',h('select',{id:periodId,'aria-label':'AM / PM',value:period,onChange:event=>setDraft(new Time(draft.hour%12+(event.target.value==='PM'?12:0),draft.minute))},
      h('option',{value:'AM'},'AM'),h('option',{value:'PM'},'PM')))),
     h('div',{className:'abs-picker-actions'},h(Button,{type:'button',onPress:()=>commit(draft)},'Apply'),
      !required?h(Button,{type:'button',onPress:()=>commit(null)},'Clear'):null,h(Button,{type:'button',onPress:()=>setOpen(false)},'Cancel'))))));
 }
 return Object.freeze({DateField,TimeField:TimeFieldControl});
}
