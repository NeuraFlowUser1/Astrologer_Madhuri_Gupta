const messages={
 contact_unavailable:'The enquiry service is temporarily unavailable. Please check your saved enquiry before trying again.',
 invalid_request:'Please check your details, including the country code if you entered a phone number.',
 verification_incorrect:'That code did not match. Please check the latest code and try again.',
 verification_changed:'A newer code was requested. Check the enquiry status, then use the latest code.',
 verification_expired:'That code has expired. Request a new one if another attempt is available.',
 verification_limit:'This request has reached its verification limit. Check its status before continuing.',
 please_wait:'Please wait before trying again. Your enquiry has not been reset.',
 access_unavailable:'We could not open this saved enquiry. Keep this page and check again, or contact the practice for help.',
 request_conflict:'This request does not match the saved enquiry. Check its status before continuing.',
 receipt_conflict:'Another saved enquiry needs to be checked before you can send a new one.',
 receipt_unavailable:'This browser could not read your saved enquiry. Please contact the practice for help.',
 storage_unavailable:'Allow this site to use browser storage before continuing. Only a private enquiry reference is stored.',
 invalid_response:'We could not safely read the response. Check the enquiry status before trying again.',
};
export const messageFor=error=>messages[error?.code] || 'The connection was interrupted. Your enquiry may have been saved. Check its status or retry the same request.';
