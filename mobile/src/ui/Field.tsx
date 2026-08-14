import { forwardRef, useState } from 'react';
import { StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { color, radius, space, type } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type FieldProps = TextInputProps & {
  label: string;
  error?: string | null;
};

/** Labelled text input. The label is always visible — no placeholder-as-label. */
export const Field = forwardRef<TextInput, FieldProps>(function Field(
  { label, error, style, onFocus, onBlur, ...rest },
  ref,
) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={styles.wrap}>
      <Txt variant="label" tone="ink3" uppercase>
        {label}
      </Txt>
      <TextInput
        ref={ref}
        style={[
          styles.input,
          focused && styles.focused,
          !!error && styles.errored,
          style,
        ]}
        placeholderTextColor={color.ink3}
        selectionColor={color.accent}
        onFocus={(e) => {
          setFocused(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          onBlur?.(e);
        }}
        accessibilityLabel={label}
        {...rest}
      />
      {error ? (
        <Txt variant="caption" tone="loss">
          {error}
        </Txt>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  wrap: { gap: space.s1, marginBottom: space.s3 },
  input: {
    backgroundColor: color.surface2,
    borderWidth: 1,
    borderColor: color.lineStrong,
    borderRadius: radius.m,
    paddingHorizontal: space.s3,
    paddingVertical: space.s3,
    fontSize: type.body.fontSize,
    color: color.ink,
  },
  focused: { borderColor: color.accent },
  errored: { borderColor: color.loss },
});
