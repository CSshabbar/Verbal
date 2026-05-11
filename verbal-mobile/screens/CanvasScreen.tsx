import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  Alert, KeyboardAvoidingView, Platform, Image, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, radius } from '../lib/theme';
import { getUserId, getDeviceName } from '../lib/storage';
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from '../lib/supabase';

type Status = 'idle' | 'saving' | 'saved' | 'error' | 'synced';

export default function CanvasScreen() {
  const [content,    setContent]    = useState('');
  const [imageUri,   setImageUri]   = useState<string | null>(null);   // local preview
  const [imageUrl,   setImageUrl]   = useState<string | null>(null);   // remote URL
  const [userId,     setUserId]     = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [status,     setStatus]     = useState<Status>('idle');
  const [statusMsg,  setStatusMsg]  = useState('');
  const [wordCount,  setWordCount]  = useState(0);

  const inputRef    = useRef<TextInput>(null);
  const isRemote    = useRef(false);
  const channelRef  = useRef<ReturnType<typeof supabase.channel> | null>(null);

  // ── Init — run once only ──────────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    (async () => {
      const uid = await getUserId();
      const dn  = await getDeviceName();
      if (!mounted) return;
      setUserId(uid);
      setDeviceName(dn);
      await loadCanvas(uid);
      subscribeCanvas(uid, dn);
    })();
    return () => {
      mounted = false;
      // Clean up channel on unmount
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current);
        channelRef.current = null;
      }
    };
  }, []); // empty deps — run once

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
        updateWordCount(data.content);
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

  // ── Realtime subscription — subscribe once, store ref ────────────────────
  const subscribeCanvas = (uid: string, dn: string) => {
    // Remove any existing channel first
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current);
    }
    const channel = supabase
      .channel(`canvas_${uid}_${Date.now()}`)   // unique name prevents conflicts
      .on('postgres_changes', {
        event:  '*',
        schema: 'public',
        table:  'canvas',
        filter: `user_id=eq.${uid}`,
      }, async (payload: any) => {
        const incoming    = (payload.new?.content  ?? '') as string;
        const incomingImg = (payload.new?.image_url ?? null) as string | null;
        const fromDevice  = (payload.new?.device_name ?? '') as string;
        if (fromDevice === dn) return;

        isRemote.current = true;
        if (incoming !== undefined) { setContent(incoming); updateWordCount(incoming); }
        if (incomingImg !== undefined) { setImageUrl(incomingImg); setImageUri(incomingImg); }

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

  const updateWordCount = (text: string) => {
    setWordCount(text.trim() ? text.trim().split(/\s+/).length : 0);
  };

  const showStatus = (s: Status, msg: string) => {
    setStatus(s); setStatusMsg(msg);
    if (s !== 'saving') setTimeout(() => { setStatus('idle'); setStatusMsg(''); }, 3000);
  };

  const handleChange = (text: string) => {
    if (isRemote.current) { isRemote.current = false; return; }
    setContent(text);
    updateWordCount(text);
    setStatus('idle'); setStatusMsg('');
  };

  // ── Image picker ──────────────────────────────────────────────────────────
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
      setImageUrl(null);   // will be set after upload
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
  };

  const removeImage = () => {
    setImageUri(null);
    setImageUrl(null);
  };

  // ── Upload image to Supabase Storage ──────────────────────────────────────
  const uploadImage = async (localUri: string): Promise<string | null> => {
    try {
      const ext      = localUri.split('.').pop()?.split('?')[0]?.toLowerCase() ?? 'jpg';
      const mime     = ext === 'png' ? 'image/png' : 'image/jpeg';
      const filename = `${userId}_${Date.now()}.${ext}`;
      const path     = `canvas/${filename}`;

      // React Native way: use FormData with the file URI directly
      const formData = new FormData();
      formData.append('file', {
        uri:  localUri,
        name: filename,
        type: mime,
      } as any);

      const uploadUrl = `${SUPABASE_URL}/storage/v1/object/canvas-images/${path}`;
      const resp = await fetch(uploadUrl, {
        method:  'POST',
        headers: {
          'apikey':        SUPABASE_ANON_KEY,
          'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
          'x-upsert':      'true',
          // Do NOT set Content-Type — let fetch set it with the boundary
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

  // ── Save & Sync ───────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!userId) {
      Alert.alert('Not configured', 'Set your User ID in Settings first.');
      return;
    }
    showStatus('saving', 'Saving…');
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

    // Upload image if we have a new local one
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
      user_id:     userId,
      content,
      image_url:   finalImageUrl ?? null,
      device_name: deviceName,
      updated_at:  new Date().toISOString(),
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
    if (!text) { Alert.alert('Clipboard is empty'); return; }
    const newContent = content ? `${content}\n\n${text}` : text;
    setContent(newContent);
    updateWordCount(newContent);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const handleClear = () => {
    Alert.alert('Clear canvas', 'Remove all content on all devices?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Clear', style: 'destructive',
        onPress: async () => {
          setContent(''); updateWordCount('');
          setImageUri(null); setImageUrl(null);
          await supabase.from('canvas').upsert({
            user_id: userId, content: '', image_url: null,
            device_name: deviceName, updated_at: new Date().toISOString(),
          }, { onConflict: 'user_id' });
          await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          showStatus('saved', 'Cleared');
        },
      },
    ]);
  };

  const statusColor =
    status === 'saved'  ? colors.green :
    status === 'synced' ? colors.accent :
    status === 'error'  ? colors.danger : colors.heroMuted;

  return (
    <KeyboardAvoidingView style={s.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {/* ── Hero ── */}
      <View style={s.hero}>
        <SafeAreaView edges={['top']}>
          <View style={s.heroRow}>
            <View>
              <Text style={s.headline}>Canvas</Text>
              <Text style={s.sub}>Shared clipboard</Text>
            </View>
            <View style={s.heroActions}>
              <TouchableOpacity style={s.iconBtn} onPress={() => loadCanvas(userId)}>
                <Ionicons name="refresh-outline" size={17} color={colors.heroText} />
              </TouchableOpacity>
              <TouchableOpacity style={s.iconBtn} onPress={handlePaste}>
                <Ionicons name="clipboard-outline" size={17} color={colors.heroText} />
              </TouchableOpacity>
              <TouchableOpacity style={s.iconBtn} onPress={pickImage}>
                <Ionicons name="image-outline" size={17} color={colors.heroText} />
              </TouchableOpacity>
              <TouchableOpacity style={[s.iconBtn, s.iconBtnDanger]} onPress={handleClear}>
                <Ionicons name="trash-outline" size={17} color={colors.accent} />
              </TouchableOpacity>
            </View>
          </View>
          <View style={s.statsRow}>
            <Text style={s.stat}><Text style={s.statVal}>{wordCount}</Text> words</Text>
            {statusMsg ? <Text style={[s.statusTxt, { color: statusColor }]}>{statusMsg}</Text> : null}
          </View>
        </SafeAreaView>
      </View>

      {/* ── Sheet ── */}
      <View style={s.sheet}>
        <ScrollView style={s.scroll} contentContainerStyle={s.scrollContent} keyboardShouldPersistTaps="handled">
          {/* Image preview */}
          {imageUri ? (
            <View style={s.imageWrap}>
              <Image source={{ uri: imageUri }} style={s.imagePreview} resizeMode="contain" />
              <View style={s.imageActions}>
                <TouchableOpacity style={s.imageActionBtn} onPress={copyImageUrl}>
                  <Ionicons name="copy-outline" size={16} color={colors.heroText} />
                  <Text style={s.imageActionTxt}>Copy URL</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.imageActionBtn, s.imageActionBtnDanger]} onPress={removeImage}>
                  <Ionicons name="trash-outline" size={16} color={colors.accent} />
                  <Text style={[s.imageActionTxt, { color: colors.accent }]}>Remove</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <TouchableOpacity style={s.imagePlaceholder} onPress={pickImage}>
              <Ionicons name="image-outline" size={28} color={colors.cardSub} />
              <Text style={s.imagePlaceholderTxt}>Tap to add image from gallery</Text>
            </TouchableOpacity>
          )}

          {/* Text input */}
          <TextInput
            ref={inputRef}
            style={s.input}
            value={content}
            onChangeText={handleChange}
            multiline
            placeholder="Type or paste text here…"
            placeholderTextColor={colors.cardSub}
            textAlignVertical="top"
            autoCorrect
          />
        </ScrollView>

        {/* Save bar */}
        <View style={s.saveBar}>
          <TouchableOpacity
            style={[s.saveBtn, status === 'saving' && s.saveBtnDisabled]}
            onPress={handleSave}
            disabled={status === 'saving'}
            activeOpacity={0.8}
          >
            <Ionicons
              name={status === 'saved' ? 'checkmark' : 'cloud-upload-outline'}
              size={16}
              color={colors.heroText}
              style={{ marginRight: 6 }}
            />
            <Text style={s.saveBtnTxt}>
              {status === 'saving' ? 'Saving…' : 'Save & Sync'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  root:               { flex: 1, backgroundColor: colors.heroBg },
  hero:               { backgroundColor: colors.heroBg, paddingHorizontal: 22, paddingBottom: 16 },
  heroRow:            { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginTop: 8 },
  headline:           { fontSize: 28, fontWeight: fonts.bold, color: colors.heroText },
  sub:                { fontSize: 12, color: colors.heroMuted, marginTop: 2 },
  heroActions:        { flexDirection: 'row', gap: 8, alignItems: 'center', marginTop: 4 },
  iconBtn:            { width: 34, height: 34, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' },
  iconBtnDanger:      { backgroundColor: 'rgba(224,90,43,0.10)' },
  statsRow:           { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 10 },
  stat:               { fontSize: 12, color: colors.heroMuted },
  statVal:            { color: colors.accent, fontWeight: fonts.semibold },
  statusTxt:          { fontSize: 11, fontStyle: 'italic', flex: 1 },

  sheet:              { flex: 1, backgroundColor: colors.sheetBg, borderTopLeftRadius: 28, borderTopRightRadius: 28, overflow: 'hidden' },
  scroll:             { flex: 1 },
  scrollContent:      { padding: 20, paddingBottom: 8 },

  imageWrap:          { marginBottom: 16, borderRadius: 12, overflow: 'hidden', backgroundColor: colors.iconGray },
  imagePreview:       { width: '100%', height: 200, borderRadius: 12 },
  imageActions:       { flexDirection: 'row', gap: 8, padding: 10, backgroundColor: colors.sheetBg },
  imageActionBtn:     { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: colors.heroBg, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8 },
  imageActionBtnDanger: { backgroundColor: 'rgba(224,90,43,0.10)' },
  imageActionTxt:     { fontSize: 12, color: colors.heroText, fontWeight: fonts.medium },
  imagePlaceholder:   { height: 100, borderRadius: 12, borderWidth: 1.5, borderColor: colors.divider, borderStyle: 'dashed', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 16 },
  imagePlaceholderTxt:{ fontSize: 12, color: colors.cardSub },

  input:              { fontSize: 15, color: colors.cardText, fontWeight: fonts.light, lineHeight: 24, minHeight: 120 },

  saveBar:            { paddingHorizontal: 20, paddingVertical: 14, borderTopWidth: 1, borderTopColor: colors.divider, backgroundColor: colors.sheetBg },
  saveBtn:            { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: colors.heroBg, borderRadius: 14, paddingVertical: 13 },
  saveBtnDisabled:    { opacity: 0.5 },
  saveBtnTxt:         { fontSize: 14, fontWeight: fonts.semibold, color: colors.heroText },
});
