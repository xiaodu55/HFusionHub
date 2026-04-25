package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Note;
import org.apache.ibatis.annotations.Mapper;

/**
 * 用户笔记 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface NoteMapper extends BaseMapper<Note> {}
