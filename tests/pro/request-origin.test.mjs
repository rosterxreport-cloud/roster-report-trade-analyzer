import test from 'node:test';
import assert from 'node:assert/strict';
import {allowedRequestOrigin} from '../../server/request-origin.mjs';
test('mutations accept configured custom, exact deployment and stable branch origins',()=>{
 const env={APP_ORIGIN:'https://www.example.com',VERCEL_URL:'build.example.vercel.app',VERCEL_BRANCH_URL:'branch.example.vercel.app'};
 for(const host of ['www.example.com','build.example.vercel.app','branch.example.vercel.app'])assert(allowedRequestOrigin('https://'+host,env));
 for(const origin of [undefined,'null','http://www.example.com','https://www.example.com/','https://www.example.com.evil.test','https://evil.test','https://branch.example.vercel.app:444'])assert(!allowedRequestOrigin(origin,env));
});
test('missing or malformed configuration cannot authorize request-supplied hosts',()=>{
 for(const env of [{},{APP_ORIGIN:'https://user:password@example.com'},{APP_ORIGIN:'https://example.com/path'},{APP_ORIGIN:'https://example.com?redirect=evil'},{VERCEL_URL:'https://example.com'},{APP_ORIGIN:'not-a-url'}])assert(!allowedRequestOrigin('https://example.com',env));
});
