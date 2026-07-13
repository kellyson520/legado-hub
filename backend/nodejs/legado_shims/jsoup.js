const cheerio = require('cheerio');

function wrapSelection(selection) {
  return {
    text() {
      return selection.text();
    },
    html() {
      return selection.html() || '';
    },
    attr(name) {
      return selection.attr(name) || '';
    },
    get(index) {
      return wrapSelection(selection.eq(index));
    },
    size() {
      return selection.length;
    },
    first() {
      return wrapSelection(selection.first());
    },
    eq(index) {
      return wrapSelection(selection.eq(index));
    },
    select(selector) {
      return wrapSelection(selection.find(selector));
    },
  };
}

function createJsoup() {
  return {
    parse(html) {
      const $ = cheerio.load(String(html || ''));
      return {
        select(selector) {
          return wrapSelection($(selector));
        },
        text() {
          return $.root().text();
        },
        html() {
          return $.root().html() || '';
        },
      };
    },
  };
}

module.exports = { createJsoup };
