import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  Alert, KeyboardAvoidingView, Platform, Image, ScrollView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { Text as FlumeText, Chip, ChipDot } from '../components';
import { colors, radius } from '../theme';
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from '../../lib/supabase';
import { getUserId, getDeviceName } from '../../lib/storage';

type Props = {};
type Status = 'idle' | 'saving' | 'saved' | 'error' | 'synced';

/**
 * Screen 4c — Canvas. Shared clipboard with real-time sync.
 * Type text or add images — saves to Supabase and syncs to all devices.
 */
export const CanvasScreen: React.FC<Props> = () => {
  const insets = useSafeAreaInsets();
  const [content, setContent] = useState('');
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [userId, setUserId] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [statusMsg, setStatusMsg] = useState('');
  const [wordCount, setWordCount] = useState(0);

  const inputRef = useRef<TextInput>(null);
  const isRemote = useRef(false);
  const channelRef = useRef<ReturnType<typeof supabase.channel> | null>(null);

  // Init — load data and subscribe to realtime changes
  useEffect(() => {
    let mounted = true;
    (async () => {
      const uid = await getUserId();
      const dn = await getDeviceName();
      if (!mounted) return;
      setUserId(uid);
      setDeviceName(dn);
      await loadCanvas(uid);
      subscribeCanvas(uid, dn);
    })();
    return () => {
      mounted = false;
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current);
        channelRef.current = null;
      }
    };
  }, []);

  const loadCanvas = async (uid: string) => {
    const { data } = await supabase
      .from('canvas')
      .select('content, image_url')
      .eq('user_id', uid)
      .single();
    if (data) {
      if (data.content) {
        isRemote.current = true;
        setContent(data.content);
        setWordCount(data.content.trim() ? data.content.trim().split(/\s+/).length : 0);
      }
      if (data.image_url) {
        setImageUrl(data.image_url);
        setImageUri(data.image_url);
      }
      if (data.content || data.image_url) {
        showStatus('synced', 'Loaded from cloud');
      }
    }
  };

  const subscribeCanvas = (uid: string, dn: string) => {
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current);
    }
    const channel = supabase
      .channel(`canvas_${uid}_${Date.now()}`)
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'canvas',
        filter: `user_id=eq.${uid}`,
      }, async (payload: any) => {
        const incoming = (payload.new?.content ?? '') as string;
        const incomingImg = (payload.new?.image_url ?? null) as string | null;
        const fromDevice = (payload.new?.device_name ?? '') as string;
        if (fromDevice === dn) return;

        isRemote.current = true;
        if (incoming !== undefined) {
          setContent(incoming);
          setWordCount(incoming.trim() ? incoming.trim().split(/\s+/).length : 0);
        }
        if (incomingImg !== undefined) {
          setImageUrl(incomingImg);
          setImageUri(incomingImg);
        }

        if (incoming) {
          await Clipboard.setStringAsync(incoming);
          await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          showStatus('synced', `↓ From ${fromDevice} · copied to clipboard`);
        } else if (incomingImg) {
          await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          showStatus('synced', `↓ Image from ${fromDevice}`);
        }
      })
      .subscribe((status, err) => {
        if (err) console.error('Canvas subscription error:', err);
      });
    channelRef.current = channel;
  };

  const showStatus = (s: Status, msg: string) => {
    setStatus(s);
    setStatusMsg(msg);
    if (s !== 'saving') {
      setTimeout(() => { setStatus('idle'); setStatusMsg(''); }, 3000);
    }
  };

  const handleChange = (text: string) => {
    if (isRemote.current) {
      isRemote.current = false;
      return;
    }
    setContent(text);
    setWordCount(text.trim() ? text.trim().split(/\s+/).length : 0);
    setStatus('idle');
    setStatusMsg('');
  };

  const pickImage = async () => {
    const { status: perm } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (perm !== 'granted') {
      Alert.alert('Permission needed', 'Allow photo library access in Settings.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
      allowsEditing: false,
    });
    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri;
      setImageUri(uri);
      setImageUrl(null);
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
  };

  const removeImage = () => {
    setImageUri(null);
    setImageUrl(null);
  };

  const uploadImage = async (localUri: string): Promise<string | null> => {
    try {
      const ext = localUri.split('.').pop()?.split('?')[0]?.toLowerCase() ?? 'jpg';
      const mime = ext === 'png' ? 'image/png' : 'image/jpeg';
      const filename = `${userId}_${Date.now()}.${ext}`;
      const path = `canvas/${filename}`;

      const formData = new FormData();
      formData.append('file', {
        uri: localUri,
        name: filename,
        type: mime,
      } as any);

      const uploadUrl = `${SUPABASE_URL}/storage/v1/object/canvas-images/${path}`;
      const resp = await fetch(uploadUrl, {
        method: 'POST',
        headers: {
          'apikey': SUPABASE_ANON_KEY,
          'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
          'x-upsert': 'true',
        },
        body: formData,
      });

      if (!resp.ok) {
        const errText = await resp.text();
        console.error('Upload error:', resp.status, errText);
        return null;
      }

      const { data } = supabase.storage.from('canvas-images').getPublicUrl(path);
      return data.publicUrl;
    } catch (e) {
      console.error('Upload failed:', e);
      return null;
    }
  };

  const handleSave = async () => {
    if (!userId) {
      Alert.alert('Not configured', 'Set your User ID in Settings first.');
      return;
    }
    showStatus('saving', 'Saving…');
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

    let finalImageUrl = imageUrl;
    if (imageUri && !imageUrl) {
      showStatus('saving', 'Uploading image…');
      finalImageUrl = await uploadImage(imageUri);
      if (!finalImageUrl) {
        showStatus('error', 'Image upload failed');
        return;
      }
      setImageUrl(finalImageUrl);
    }

    const { error } = await supabase.from('canvas').upsert({
      user_id: userId,
      content,
      image_url: finalImageUrl ?? null,
      device_name: deviceName,
      updated_at: new Date().toISOString(),
    }, { onConflict: 'user_id' });

    if (error) {
      showStatus('error', `Save failed: ${error.message}`);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      return;
    }

    if (content) await Clipboard.setStringAsync(content);
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    showStatus('saved', '✓ Saved & synced');
  };

  const copyImageUrl = async () => {
    if (!imageUrl) return;
    await Clipboard.setStringAsync(imageUrl);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    showStatus('saved', 'Image URL copied to clipboard');
  };

  const handlePaste = async () => {
    const text = await Clipboard.getStringAsync();
    if (!text) {
      Alert.alert('Clipboard is empty');
      return;
    }
    const newContent = content ? `${content}\n\n${text}` : text;
    setContent(newContent);
    setWordCount(newContent.trim() ? newContent.trim().split(/\s+/).length : 0);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const handleClear = () => {
    Alert.alert('Clear canvas', 'Remove all content on all devices?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Clear',
        style: 'destructive',
        onPress: async () => {
          setContent('');
          setWordCount(0);
          setImageUri(null);
          setImageUrl(null);
          await supabase.from('canvas').upsert({
            user_id: userId,
            content: '',
            image_url: null,
            device_name: deviceName,
            updated_at: new Date().toISOString(),
          }, { onConflict: 'user_id' });
          await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          showStatus('saved', 'Cleared');
        },
      },
    ]);
  };

  const handleReload = async () => {
    await loadCanvas(userId);
    showStatus('synced', 'Reloaded from cloud');
  };

const ActionBtn: React.FC<{ icon: any; label: string; onPress: () => void }> = ({
  icon, label, onPress,
}) => {
  const handlePress = React.useCallback(async () => {
    try {
      await Haptics.selectionAsync();
      await onPress();
    } catch (err) {
      console.error('ActionBtn press error:', err);
    }
  }, [onPress]);

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => [styles.actionBtn, pressed && { opacity: 0.8 }]}
    >
      <Ionicons name={icon} size={22} color={colors.textPrimary} />
      <Text variant="buttonSm">{label}</Text>
    </Pressable>
  );
};

const Item: React.FC<{
  item: CanvasItem;
  onSave: (id: string) => void;
  onDiscard: (id: string) => void;
  targetName: string;
}> = ({ item, onSave, onDiscard, targetName }) => {
  const isDraft = item.state === 'draft';
  const isSent  = item.state === 'sent';

  return (
    <Card padding={12} emphasis={isDraft ? 'draft' : 'default'}>
      {item.kind === 'text' && (
        <Text variant="bodySm" style={{ marginBottom: 8 }}>"{item.text}"</Text>
      )}
      {item.kind === 'link' && (
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 8 }}>
          <View style={styles.linkIcon}>
            <Ionicons name="link" size={22} color={colors.textPrimary} />
          </View>
          <View style={{ flex: 1, justifyContent: 'center', minWidth: 0 }}>
            <Text variant="button" numberOfLines={1}>{item.url}</Text>
          </View>
        </View>
      )}
      {item.kind === 'image' && (
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 8 }}>
          <Image
            source={{ uri: item.uri }}
            style={styles.thumb}
            resizeMode="cover"
          />
          <View style={{ flex: 1, justifyContent: 'center' }}>
            <Text variant="button">{item.filename}</Text>
            <Text variant="caption" color={colors.textMuted}>
              {item.sizeLabel ?? ''} {item.dimensions ? `· ${item.dimensions}` : ''}
            </Text>
          </View>
        </View>
      )}

      {isDraft ? (
        <View style={styles.footerRow}>
          <Text variant="metaSm" color={colors.primary}>DRAFT · {item.kind.toUpperCase()}</Text>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <Pressable onPress={() => onDiscard(item.id)} style={{ padding: 4 }}>
              <Text variant="buttonSm" color={colors.textMuted}>Discard</Text>
            </Pressable>
            <Pressable onPress={() => onSave(item.id)} style={styles.savePill}>
              <Text variant="buttonSm" color={colors.primaryInk}>
                Save → {targetName.split(' ')[0]}
              </Text>
            </Pressable>
          </View>
        </View>
      ) : (
        <View style={styles.footerRow}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            <View style={{ width: 5, height: 5, borderRadius: 2.5, backgroundColor: colors.online }} />
            <Text variant="metaSm" color={colors.online}>
              SENT · {item.sentAt} · {item.kind.toUpperCase()}
            </Text>
          </View>
        </View>
      )}
    </Card>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionBar: {
    flexDirection: 'row',
    gap: 6,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    borderRadius: radius.lg,
    backgroundColor: colors.surface2,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  linkIcon: {
    width: 42,
    height: 42,
    borderRadius: radius.sm,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  thumb: {
    width: 60,
    height: 60,
    borderRadius: radius.sm,
    backgroundColor: colors.surface2,
  },
  footerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  savePill: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: radius.xs,
    backgroundColor: colors.primary,
  },
});

export default CanvasScreen;
