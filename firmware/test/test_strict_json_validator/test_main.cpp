#include <unity.h>

#include <string.h>

#include "protocol/StrictJsonValidator.h"

using namespace labforge;

LexicalError check(const char* value) {
  return StrictJsonValidator().validate(reinterpret_cast<const uint8_t*>(value), strlen(value));
}

void test_valid_ascii_and_multibyte_json() {
  TEST_ASSERT_EQUAL(LexicalError::NONE, check("{\"a\":true,\"b\":-12}"));
  const uint8_t utf8[] = {'{', '"', 'a', '"', ':', '"', 0xC5, 0xBE, '"', '}'};
  TEST_ASSERT_EQUAL(LexicalError::NONE, StrictJsonValidator().validate(utf8, sizeof(utf8)));
}

void test_invalid_utf8_forms() {
  const uint8_t continuation[] = {'"', 0x80, '"'};
  const uint8_t overlong[] = {'"', 0xC0, 0xAF, '"'};
  const uint8_t truncated[] = {'"', 0xE2, 0x82};
  const uint8_t surrogate[] = {'"', 0xED, 0xA0, 0x80, '"'};
  const uint8_t tooHigh[] = {'"', 0xF4, 0x90, 0x80, 0x80, '"'};
  TEST_ASSERT_EQUAL(LexicalError::INVALID_UTF8, StrictJsonValidator().validate(continuation, sizeof(continuation)));
  TEST_ASSERT_EQUAL(LexicalError::INVALID_UTF8, StrictJsonValidator().validate(overlong, sizeof(overlong)));
  TEST_ASSERT_EQUAL(LexicalError::INVALID_UTF8, StrictJsonValidator().validate(truncated, sizeof(truncated)));
  TEST_ASSERT_EQUAL(LexicalError::INVALID_UTF8, StrictJsonValidator().validate(surrogate, sizeof(surrogate)));
  TEST_ASSERT_EQUAL(LexicalError::INVALID_UTF8, StrictJsonValidator().validate(tooHigh, sizeof(tooHigh)));
}

void test_embedded_nul_and_non_json_extensions() {
  const uint8_t nul[] = {'{', '}', 0, 'x'};
  TEST_ASSERT_EQUAL(LexicalError::EMBEDDED_NUL, StrictJsonValidator().validate(nul, sizeof(nul)));
  const char* invalid[] = {"{'a':1}", "{/*x*/\"a\":1}", "{\"a\":NaN}", "{\"a\":Infinity}",
                           "{\"a\":-Infinity}", "{}x", "{\"a\":}"};
  for (const char* value : invalid) TEST_ASSERT_EQUAL(LexicalError::MALFORMED_JSON, check(value));
}

void test_duplicate_keys_are_exact_and_recursive() {
  TEST_ASSERT_EQUAL(LexicalError::DUPLICATE_KEY, check("{\"a\":1,\"a\":2}"));
  TEST_ASSERT_EQUAL(LexicalError::DUPLICATE_KEY, check("{\"arguments\":{\"x\":1,\"x\":2}}"));
  TEST_ASSERT_EQUAL(LexicalError::DUPLICATE_KEY, check("{\"a\":1,\"\\u0061\":2}"));
  TEST_ASSERT_EQUAL(LexicalError::DUPLICATE_KEY,
                    check("{\"type\":\"HELLO\",\"\\u0074ype\":\"HELLO\"}"));
  TEST_ASSERT_EQUAL(LexicalError::DUPLICATE_KEY,
                    check("{\"arguments\":{\"value\":1,\"\\u0076alue\":2}}"));
}

void test_duplicate_keys_use_decoded_bytes_and_lengths() {
  TEST_ASSERT_EQUAL(LexicalError::DUPLICATE_KEY,
                    check("{\"a\\u0000b\":1,\"a\\u0000b\":2}"));
  TEST_ASSERT_EQUAL(LexicalError::NONE, check("{\"a\":1,\"a\\u0000b\":2}"));
  TEST_ASSERT_EQUAL(LexicalError::NONE, check("{\"type\":1,\"type\\u0000x\":2}"));
  TEST_ASSERT_EQUAL(LexicalError::DUPLICATE_KEY, check("{\"a\":1,\"\\u0061\":2}"));
  TEST_ASSERT_EQUAL(LexicalError::DUPLICATE_KEY, check("{\"plain\":1,\"plain\":2}"));
}

void test_tokens_inside_strings_are_ordinary_content() {
  const char* valid[] = {"{\"value\":\"NaN\"}", "{\"value\":\"Infinity\"}",
                         "{\"value\":\"-Infinity\"}", "{\"value\":\"// not a comment\"}",
                         "{\"value\":\"/* not a comment */\"}",
                         "{\"value\":\"apostrophe ' is valid here\"}"};
  for (const char* value : valid) TEST_ASSERT_EQUAL(LexicalError::NONE, check(value));
}

void test_json_string_escape_rules() {
  TEST_ASSERT_EQUAL(LexicalError::NONE,
                    check("{\"value\":\"quote: \\\" slash: \\\\ newline: \\n tab: \\t letter: \\u0061\"}"));
  TEST_ASSERT_EQUAL(LexicalError::NONE, check("{\"value\":\"\\ud83d\\ude00\"}"));
  TEST_ASSERT_EQUAL(LexicalError::MALFORMED_JSON, check("{\"value\":\"\\x41\"}"));
  TEST_ASSERT_EQUAL(LexicalError::MALFORMED_JSON, check("{\"value\":\"\\u123\"}"));
  TEST_ASSERT_EQUAL(LexicalError::MALFORMED_JSON, check("{\"value\":\"\\ud800\"}"));
  TEST_ASSERT_EQUAL(LexicalError::MALFORMED_JSON, check("{\"value\":\"\\udc00\"}"));
}

void test_strict_number_grammar_and_integer_only_policy() {
  const char* valid[] = {"0", "-1", "9223372036854775807", "-9223372036854775808"};
  for (const char* value : valid) TEST_ASSERT_EQUAL(LexicalError::NONE, check(value));
  const char* malformed[] = {"01", "+1", "1.", ".1", "1e", "1e+", "--1"};
  for (const char* value : malformed) TEST_ASSERT_EQUAL(LexicalError::MALFORMED_JSON, check(value));
  TEST_ASSERT_EQUAL(LexicalError::NON_INTEGER_NUMBER, check("1.0"));
  TEST_ASSERT_EQUAL(LexicalError::NON_INTEGER_NUMBER, check("1e2"));
}

void test_nesting_depth_empty_and_nonempty_containers_match() {
  const char* boundary[] = {"{\"value\":{}}", "{\"value\":{\"x\":1}}",
                            "{\"value\":[]}", "{\"value\":[1]}"};
  for (const char* value : boundary) TEST_ASSERT_EQUAL(LexicalError::NONE, check(value));

  const char* overDepth[] = {"{\"arguments\":{\"value\":{}}}",
                             "{\"arguments\":{\"value\":{\"x\":1}}}",
                             "{\"arguments\":{\"value\":[]}}",
                             "{\"arguments\":{\"value\":[1]}}"};
  for (const char* value : overDepth) {
    TEST_ASSERT_EQUAL(LexicalError::MALFORMED_JSON, check(value));
  }
  TEST_ASSERT_EQUAL(LexicalError::NONE, check("{\"arguments\":{\"value\":1}}"));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_valid_ascii_and_multibyte_json);
  RUN_TEST(test_invalid_utf8_forms);
  RUN_TEST(test_embedded_nul_and_non_json_extensions);
  RUN_TEST(test_duplicate_keys_are_exact_and_recursive);
  RUN_TEST(test_duplicate_keys_use_decoded_bytes_and_lengths);
  RUN_TEST(test_tokens_inside_strings_are_ordinary_content);
  RUN_TEST(test_json_string_escape_rules);
  RUN_TEST(test_strict_number_grammar_and_integer_only_policy);
  RUN_TEST(test_nesting_depth_empty_and_nonempty_containers_match);
  return UNITY_END();
}
