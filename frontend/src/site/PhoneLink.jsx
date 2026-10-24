import {practiceContact} from './practice-contact.mjs';

/** A native call action, without a custom handler or booking dependency. */
export default function PhoneLink({className = ''}) {
  return <a className={'practice-phone '+className} href={practiceContact.phoneHref} aria-label={'Call Sarsa at '+practiceContact.phoneDisplay}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.2 3.5 10 7.8 7.8 10a15.4 15.4 0 0 0 6.2 6.2l2.2-2.2 4.3 1.8v3.8a1.4 1.4 0 0 1-1.5 1.4A17.5 17.5 0 0 1 3 5a1.4 1.4 0 0 1 1.4-1.5Z"/></svg>
    <span>{practiceContact.phoneDisplay}</span>
  </a>;
}
